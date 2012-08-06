"""

  This script performs a comparison between the performance of networks specified with NINEML+ and
  the legacy hoc code.

  @file comparison.py
  @author Tom Close

"""

#######################################################################################
#
#    Copyright 2011 Okinawa Institute of Science and Technology (OIST), Okinawa, Japan
#
#######################################################################################
import sys
import os.path
if 'NINEMLP_MPI' in os.environ:
    import mpi4py #@UnresolvedImport @UnusedImport
    print "importing MPI"
from backports import argparse
import ninemlp
import math
#from pyNN.random import RandomDistribution, NumpyRNG
import numpy.random

if 'NRNHOME' in os.environ:
    os.environ['PATH'] += os.pathsep + os.environ['NRNHOME']
else:
    os.environ['PATH'] += os.pathsep + '/opt/NEURON-7.2/x86_64/bin' # Sorry this is the path on my machine (to save me having to set the environment variable in eclipse)

PROJECT_PATH = os.path.normpath(os.path.join(ninemlp.SRC_PATH, '..'))
NETWORK_XML_LOCATION = os.path.join(PROJECT_PATH, 'xml/cerebellum', 'fabios_network.xml')

parser = argparse.ArgumentParser(description='A script to ')
parser.add_argument('--simulator', type=str, default='neuron',
                                           help="simulator for NINEML+ (either 'neuron' or 'nest')")
parser.add_argument('--build', type=str, default=ninemlp.BUILD_MODE,
                            help='Option to build the NMODL files before running (can be one of \
                            %s.' % ninemlp.BUILD_MODE_OPTIONS)
parser.add_argument('--mf_rate', type=float, default=1, help='Mean firing rate of the Mossy Fibres')
parser.add_argument('--time', type=float, default=2000.0, help='The run time of the simulation (ms)')
parser.add_argument('--output', type=str, default=os.path.join(PROJECT_PATH, 'fabios_network.out') , help='The output location of the recording files')
parser.add_argument('--start_input', type=float, default=1000, help='The start time of the mossy fiber stimulation')
parser.add_argument('--min_delay', type=float, default=0.0005, help='The minimum synaptic delay in the network')
parser.add_argument('--timestep', type=float, default=0.00005, help='The timestep used for the simulation')
parser.add_argument('--save_connections', type=str, default=None, help='A path in which to save the generated connections')
parser.add_argument('--stim_seed', type=int, default=123456, help='The seed passed to the stimulated spikes')
parser.add_argument('--para_unsafe', action='store_true', help='If set the network simulation will try to be parallel neuron safe')
args = parser.parse_args()

numpy.random.seed(args.stim_seed)

print "Simulation time: %f" % args.time
print "Stimulation start: %f" % args.start_input
print "MossyFiber firing rate: %f" % args.mf_rate

ninemlp.BUILD_MODE = args.build

exec("from ninemlp.%s import *" % args.simulator)
#from pyNN.random import RandomDistribution

setup(timestep=args.timestep, min_delay=args.min_delay, max_delay=2.0) #@UndefinedVariable

print "Building network"

net = Network(NETWORK_XML_LOCATION) #@UndefinedVariable

if args.build == 'compile_only':
    print "Compiled Fabio's Network and now exiting ('--build' option was set to 'compile_only')"
    sys.exit(0)

mossy_fiber_inputs = net.get_population('MossyFiberInputs')
golgis = net.get_population('Golgis')

# TODO: Change warning message for incorrect number of connections, using warning module

print "Setting up simulation"
mean_interval = 1000 / args.mf_rate # Convert from Hz to ms
stim_range = args.time - args.start_input # Is scaled by 50% just to be sure it doesn't end early
if stim_range >= 0.0:
    num_spikes = stim_range / mean_interval
    num_spikes = int(num_spikes + math.exp(-num_spikes / 10.0) * 10.0) # Add extra spikes to account for variability in numbers
    mf_spike_intervals = numpy.random.exponential(mean_interval, size=(mossy_fiber_inputs.size, num_spikes))
    mf_spike_times = numpy.cumsum(mf_spike_intervals, axis=1)
    mossy_fiber_inputs.tset('spike_times', mf_spike_times)
else:
    print "Warning, stimulation start (%f) is after end of experiment (%f)" % \
                                                                    (args.start_input, args.time)

for pop in net.all_populations():
    record(pop, args.output + "." + pop.label + ".spikes") #@UndefinedVariable
    if pop.label != 'MossyFiberInputs':
        record_v(pop, args.output + "." + pop.label + ".v") #@UndefinedVariable

print "Final Network is..."

print "Populations:"
for pop in net.all_populations():
    print pop.describe()

print "Projections:"
for proj in net.all_projections():
    print proj.describe()
    if args.save_connections:
        proj.saveConnections(os.path.join(args.save_connections, proj.label))

print "Starting run"

run(args.time) #@UndefinedVariable

end() #@UndefinedVariable

print "Simulated Fabio's Network for %f milliseconds" % args.time
