"""
  Contains functions to set up the environment on the tombo server to run scripts in the 'simulate' 
  package
  
  @author Tom Close 
"""
import sys
if float(sys.version[0:3]) < 2.7:
    raise Exception("This script requires python version 2.7 or greater, you should add python 2.7 to your path (i.e. PATH=$PATH:/apps/python/272/bin)")
import os
import time
import shutil
import subprocess
from copy import copy

UNIT_MEMBERS = {'deschutter': ['tclose', 'mnegrello', 'raikov', 'dguo', 'shyamkumar'],
                'doya': ['otsuka','jun-y', 'shauno']}

UNIT_WORK_DIRS = {'deschutter': 'DeschutterU',
                  'doya': 'DoyaU'}

def get_project_dir():
    """
    Returns the root directory of the project
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')) # Root directory of the project code

def create_seed(seed):
    if not seed:
        seed = long(time.time() * 256)
    else:
        seed = int(seed)
    return seed

def create_work_dir(script_name, output_parent_dir=None, required_dirs=['src', 'xml'], username=None):
    """
    Generates unique paths for the work and output directories, creating the work directory in the 
    process.
    
    @param script_name: The name of the script, used to name the directories appropriately
    @param output_parent_dir: The name of the parent directory in which the output directory will be created (defaults to $HOME/Output).
    @param required_dirs: The sub-directories that need to be copied into the work directory    
    @param username: The username of the user, in order to get the appropriate work directory for them (defaults to login username).
    """
    if not output_parent_dir:
        output_parent_dir = os.path.join(os.environ['HOME'], 'Output')
    if not username:
        username = os.getlogin()
    unit_dir = None
    for unit, members in UNIT_MEMBERS.iteritems():
        if username in members:
            unit_dir = UNIT_WORK_DIRS[unit]
            break        
    if not unit_dir:
        raise Exception("Unrecognised user '%s', please edit tombo/fabios_network.py to specifiy which unit they belong to in the tombo.UNIT_MEMBERS directory.")
    # Automatically generate paths
    time_str = time.strftime('%Y-%m-%d-%A_%H-%M-%S', time.localtime()) # Unique time for distinguishing runs    
    work_dir = os.path.join('/work', unit_dir, username, script_name + "." + time_str + ".1") # Working directory path
    #Ensure that working directory is unique
    created_work_dir=False
    count = 1
    while not created_work_dir:
        try:
            created_work_dir = not os.makedirs(work_dir) 
        except IOError as e:
            count += 1
            if count > 1000:
                print "Something has gone wrong, can't create directory '%s' after 1000 attempts" % work_dir
                raise e
            work_dir = '.'.join(work_dir.split('.')[:-1] + [str(count)]) # Replace old count at the end of work directory with new count
    output_dir = os.path.join(output_parent_dir, os.path.split(work_dir)[1])
    init_work_dir(work_dir, required_dirs, time_str)   
    return work_dir, output_dir

def init_work_dir(work_dir, required_dirs, time_str):
    """
    Copies directories from the project directory to the work directory
    
    @param work_dir: The destination work directory
    @param required_dirs: The required sub-directories to be copied to the work directory
    """
    # Copy snapshot of selected subdirectories to working directory
    for directory in required_dirs:
        shutil.copytree(os.path.join(get_project_dir(),directory), os.path.join(work_dir,directory), symlinks=True)
    # Make output directory for the generated files
    os.mkdir(os.path.join(work_dir, 'output'))
    # Save the git revision in the output folder for reference
    subprocess.call('cd %s; git rev-parse HEAD > %s' % (get_project_dir(), os.path.join(work_dir, 'output', 'git_revision')), shell=True)
    # Write time string to file for future reference
    f = open(os.path.join(work_dir, 'output', 'time_stamp'), 'w')
    f.write(time_str)
    f.close()
    


def create_env(work_dir):
    """
    Creates a dictionary containing the appropriate environment variables
    
    @param work_dir: The work directory to set the envinroment variables for
    """
    env = os.environ.copy()
    env['PATH'] = env['PATH'] + os.pathsep + \
                  '/apps/python/272/bin' + os.pathsep + \
                  '/opt/mpi/gnu/openmpi-1.4.3/bin' + os.pathsep + \
                  '/apps/DeschutterU/NEURON-7.2/x86_64/bin'
    env['PYTHONPATH'] = os.path.join(work_dir, 'src')
    env['LD_LIBRARY_PATH'] = '/opt/mpi/gnu/openmpi-1.4.3/lib'
    env['NINEML_SRC_PATH'] = os.path.join(work_dir, 'src')
    return env
    
def compile_ninemlp(script_name, work_dir, env=None, script_dir='simulate'):
    """
    Compiles objects in the work directory that are required by the NINEML+ network
    
    @param script_name: Name of the script in the 'simulate' directory
    @param work_dir: The work directory in which the network is compiled
    @param env: The required environment variables (defaults to those generated by 'create_env(work_dir)')
    @param script_dir: The directory that the script is stored in (default: 'simulate')
    """
    if not env:
        env = create_env(work_dir)
    else:
        env = copy(env)
    env['NINEMLP_BUILD_MODE'] = 'compile_only'
    env['NINEMLP_MPI'] = '1'
    print "Compiling required NINEML+ objects"
    subprocess.check_call('python %s --build compile_only' %
                                      os.path.join(work_dir, 'src', script_dir, script_name + '.py'),
                                                                       shell=True, env=env)
    


def submit_job(script_name, cmds, np, work_dir, output_dir, env=None, copy_to_output=['xml'], strip_build_from_copy=True):
    """
    Create a jobscript in the work directory and then submit it to the tombo que
    
    @param script_name: The name of the script (used to give a meaningful name to the job)
    @param cmds: The commands to run on the cluster
    @param np: The number of processors to request for the job
    @param work_dir: The working directory to run the script from
    @param output_dir: The output directory to copy the results to
    @param env: The required environment variables (defaults to those generated by 'create_env(work_dir)')    
    @param copy_to_output: Directories to copy into the output directory
    @param strip_build_from_copy: Removes all files and directories to be copied that have the name 'build'
    """
    if not env:
        env = create_env(work_dir)
    else:
        env = copy(env)
    copy_cmd = ''
    for directory in copy_to_output:
        if strip_build_from_copy:
            copy_cmd+='find {work_dir}/{directory} -name build -exec rm -r {{}} \; 2>/dev/null\n'.format(work_dir=work_dir, directory=directory)
        copy_cmd+='mv {work_dir}/{directory} {output_dir}/{directory}\n'.format(work_dir=work_dir, output_dir=output_dir, directory=directory)
    #Create jobscript
    jobscript_path = os.path.join(work_dir, script_name + '.job')
    f = open(jobscript_path, 'w')
    f.write("""#!/usr/bin/env sh
    
# Parse the job script using this shell
#$ -S /bin/bash

# Send stdout and stderr to the same file.
#$ -j y

# Standard output and standard error files
#$ -o {work_dir}/output_stream
#$ -e {work_dir}/output_stream

# Name of the queue
#$ -q longP

# use OpenMPI parallel environment with {np} processes
#$ -pe openmpi {np}

# Export the following env variables:
#$ -v HOME
#$ -v PATH
#$ -v PYTHONPATH
#$ -v LD_LIBRARY_PATH
#$ -v NINEMLP_SRC_PATH
#$ -v NINEMLP_BUILD_MODE
#$ -v NINEMLP_MPI
#$ -v BREP_DEVEL
#$ -v PARAMDIR
#$ -v VERBOSE

###################################################
### Copy the model to all machines we are using ###
###################################################

# Set up the correct paths 
export PATH={path}:$PATH
export PYTHONPATH={pythonpath}
export LD_LIBRARY_PATH={ld_library_path}
export NINEMLP_SRC_PATH={ninemlp_src_path}
export NINEMLP_BUILD_MODE='lazy'
export NINEMLP_MPI=1

echo "============== Starting mpirun ===============" 

cd {work_dir}
{cmds}

echo "============== Mpirun has ended - Copying files to output directory '{output_dir}' =============="
mv {work_dir}/output {output_dir}
cp {jobscript_path} {output_dir}/job
cp {work_dir}/output_stream {output_dir}/output
{copy_cmd}
echo "============== Done ===============" 
""".format(work_dir=work_dir, path=env['PATH'], pythonpath=env['PYTHONPATH'],
      ld_library_path=env['LD_LIBRARY_PATH'], ninemlp_src_path=os.path.join(work_dir,'src'), np=np,
      cmds=cmds, output_dir=output_dir, copy_cmd=copy_cmd,
      jobscript_path=jobscript_path))
    f.close()
    # Submit job
    print "Submitting job '%s' to que" % jobscript_path
    subprocess.check_call('qsub %s' % jobscript_path, shell=True)
    print "Your job '%s' has been submitted" % jobscript_path
    print "While the job is running, its output stream can be viewed by:"
    print "less " + os.path.join(work_dir, 'output_stream')
    print "Once completed the output files (including the output stream and job script) of this job will be copied to:"
    print output_dir
