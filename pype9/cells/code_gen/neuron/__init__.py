"""

  This module contains functions for building and loading NMODL mechanisms

  Author: Thomas G. Close (tclose@oist.jp)
  Copyright: 2012-2014 Thomas G. Close.
  License: This file is part of the "NineLine" package, which is released under
           the MIT Licence, see LICENSE for details.
"""
from __future__ import absolute_import
import os.path
import shutil
import time
from itertools import chain
import platform
import tempfile
import uuid
import subprocess as sp
import quantities as pq
from .. import BaseCodeGenerator
import nineml.abstraction_layer.units as un
from nineml.abstraction_layer.dynamics import OnEvent, TimeDerivative
from pype9.exceptions import Pype9BuildError
import pype9
from datetime import datetime
from nineml.utils import expect_single


if 'NRNHOME' in os.environ:
    os.environ['PATH'] += (os.pathsep +
                           os.path.join(os.environ['NRNHOME'],
                                        platform.machine(), 'bin'))
else:
    try:
        if os.environ['HOME'] == '/home/tclose':
            # I apologise for this little hack (this is the path on my machine,
            # to save me having to set the environment variable in eclipse)
            os.environ['PATH'] += os.pathsep + '/opt/NEURON/nrn-7.3/x86_64/bin'
    except KeyError:
        pass


class CodeGenerator(BaseCodeGenerator):

    SIMULATOR_NAME = 'neuron'
    ODE_SOLVER_DEFAULT = 'derivimplicit'
    SS_SOLVER_DEFAULT = 'gsl'
    MAX_STEP_SIZE_DEFAULT = 0.01  # FIXME:!!!
    ABS_TOLERANCE_DEFAULT = 0.01
    REL_TOLERANCE_DEFAULT = 0.01
    V_THRESHOLD_DEFAULT = 0.0
    FIRST_REGIME_FLAG = 1001
    FIRST_TRANSITION_FLAG = 5000
    _TMPL_PATH = os.path.join(os.path.dirname(__file__), 'jinja_templates')

    _neuron_units = {un.mV: 'millivolt',
                     un.S: 'siemens',
                     un.mA: 'milliamp'}

    _inbuilt_ions = ['na', 'k', 'ca']

    def __init__(self):
        super(CodeGenerator, self).__init__()
        # Find the path to nrnivmodl
        self.nrnivmodl_path = self.path_to_exec('nrnivmodl')
        # Work out the name of the installation directory for the compiled
        # NMODL files on the current platform
        self.specials_dir = self._get_specials_dir()

    def generate_source_files(self, component, initial_state, src_dir,  # @UnusedVariable @IgnorePep8
                              **kwargs):
        componentclass = component.component_class
        tmpl_args = {
            'component': component,
            'componentclass': componentclass,
            'version': pype9.version, 'src_dir': src_dir,
            'timestamp': datetime.now().strftime('%a %d %b %y %I:%M:%S%p'),
            'ode_solver': kwargs.get('ode_solver', self.ODE_SOLVER_DEFAULT),
            'unit_conversion': self.unit_conversion,
            'parameter_scales': [], 'membrane_voltage': 'V_t',
            'v_threshold': kwargs.get('v_threshold', self.V_THRESHOLD_DEFAULT),
            'weight_variables': [],
            'deriv_func_args': self.deriv_func_args, 'ode_for': self.ode_for,
            'all_time_derivs': list(chain(*(r.time_derivatives
                                            for r in componentclass.regimes)))}
        # Render mod file
        self.render_to_file('main.tmpl', tmpl_args, component.name + '.mod',
                            src_dir)

    def configure_build_files(self, component, src_dir, compile_dir,
                               install_dir):
        pass

    def compile_source_files(self, compile_dir, component_name, verbose):
        """
        Builds all NMODL files in a directory
        @param src_dir: The path of the directory to build
        @param build_mode: Can be one of either, 'lazy', 'super_lazy',
                           'require', 'force', or 'build_only'. 'lazy' doesn't
                           run nrnivmodl if the library is found, 'require',
                           requires that the library is found otherwise throws
                           an exception (useful on clusters that require
                           precompilation before parallelisation where the
                           error message could otherwise be confusing), 'force'
                           removes existing library if found and recompiles,
                           and 'build_only' removes existing library if found,
                           recompile and then exit
        @param verbose: Prints out verbose debugging messages
        """
        # Change working directory to model directory
        os.chdir(compile_dir)
        if verbose:
            print ("Building NEURON mechanisms in '{}' directory."
                   .format(compile_dir))
        # Run nrnivmodl command in src directory
        try:
            if not verbose:
                with open(os.devnull, "w") as fnull:
                    sp.check_call(self.nrnivmodl_path, stdout=fnull,
                                  stderr=fnull)
            else:
                sp.check_call(self.nrnivmodl_path)
        except sp.CalledProcessError as e:
            raise Pype9BuildError(
                "Compilation of NMODL files for '{}' model failed. See src "
                "directory '{}':\n ".format(component_name, compile_dir, e))

    def get_install_dir(self, build_dir, install_dir):
        if install_dir:
            raise Pype9BuildError(
                "Cannot specify custom installation directory ('{}') for "
                "NEURON simulator as it needs to be located as a specifically "
                "named directory of the src directory (e.g. x86_64 for 64b "
                "unix/linux)".format(install_dir))
        # return the platform-specific location of the nrnivmodl output files
        return os.path.abspath(os.path.join(build_dir, self._SRC_DIR,
                                            self.specials_dir))

    def get_compile_dir(self, build_dir):
        """
        The compile dir is the same as the src dir for NEURON compile
        """
        return os.path.abspath(os.path.join(build_dir, self._SRC_DIR))

    def clean_compile_dir(self, compile_dir):
        pass  # NEURON doesn't use a separate compile dir

    def _get_specials_dir(self):
        # Create a temporary directory to run nrnivmodl in
        tmp_dir_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            os.mkdir(tmp_dir_path)
        except IOError:
            raise Pype9BuildError("Error creating temporary directory '{}'"
                                  .format(tmp_dir_path))
        orig_dir = os.getcwd()
        os.chdir(tmp_dir_path)
        # Run nrnivmodl to see what build directory is created
        try:
            with open(os.devnull, "w") as fnull:
                sp.check_call(self.nrnivmodl_path, stdout=fnull, stderr=fnull)
        except sp.CalledProcessError as e:
            raise Pype9BuildError("Error test running nrnivmodl".format(e))
        # Get the name of the specials directory
        try:
            specials_dir = os.listdir(tmp_dir_path)[0]
        except IndexError:
            raise Pype9BuildError(
                "Error test running nrnivmodl no build directory created"
                .format(e))
        # Return back to the original directory
        os.chdir(orig_dir)
        return specials_dir

    def simulator_specific_paths(self):
        path = []
        try:
            for d in os.listdir(os.environ['NRNHOME']):
                bin_path = os.path.join(d, 'bin')
                if os.path.exists(bin_path):
                    path.append(bin_path)
        except KeyError:
            pass
        return path

    @classmethod
    def deriv_func_args(cls, component, variable):
        """ """
        args = set([variable])
        for r in component.regimes:
            for time_derivative in (eq for eq in r.time_derivatives
                                    if eq.dependent_variable == variable):
                for name in (name for name in time_derivative.rhs_names
                             if name in [sv.name
                                         for sv in component.state_variables]):
                    args.add(name)
        return ','.join(args)
        return args

    @classmethod
    def ode_for(cls, regime, variable):
        """
        Yields the TimeDerivative for the given variable in the regime
        """
        odes = [eq for eq in regime.time_derivatives
                if eq.dependent_variable == variable.name]
        if len(odes) == 0:
            odes.append(TimeDerivative(dependent_variable=variable, rhs="0.0"))
        return expect_single(odes)