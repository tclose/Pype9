"""

  This module contains functions for building and loading NMODL mechanisms

  Author: Thomas G. Close (tclose@oist.jp)
  Copyright: 2012-2014 Thomas G. Close.
  License: This file is part of the "NineLine" package, which is released under
           the MIT Licence, see LICENSE for details.
"""
from __future__ import absolute_import
import os.path
import tempfile
from copy import copy
import uuid
import subprocess as sp
from ..base import BaseCodeGenerator
import nineml.abstraction_layer.units as un
from nineml.abstraction_layer.dynamics import (
    OnEvent, TimeDerivative, StateVariable)
from nineml.abstraction_layer.expressions import Alias
from nineml.abstraction_layer.ports import (
    AnalogReceivePort, AnalogSendPort)
from pype9.exceptions import (
    Pype9BuildError, Pype9RuntimeError,
    Pype9CouldNotGuessFromDimensionException,
    Pype9NoElementWithMatchingDimensionException)
import pype9
from datetime import datetime
from nineml import Document
from nineml.user_layer import Dynamics, Definition, Property
from nineml.abstraction_layer import Parameter
try:
    from nineml.extensions.kinetics import Kinetics
except ImportError:
    KineticsClass = type(None)
from pype9 import PYPE9_NS
from ...neuron import ION_SPECIES_NS
import logging

TRANSFORM_NS = 'NeuronBuildTransform'

logger = logging.getLogger("PyPe9")


class CodeGenerator(BaseCodeGenerator):

    SIMULATOR_NAME = 'neuron'
    ODE_SOLVER_DEFAULT = 'derivimplicit'
    _TMPL_PATH = os.path.join(os.path.dirname(__file__), 'templates')

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

    def generate_source_files(self, name, prototype, initial_state, src_dir,
                              **kwargs):
        """
            *KWArgs*
                `membrane_voltage` -- Specifies the state that represents
                                      membrane voltage.
                `v_threshold`      -- The threshold for the neuron to emit a
                                      spike.
                `external_ports`   -- Analog ports to strip from expressions
                                      as they represent synapses or injected
                                      currents, which can be inserted manually
                                      by NEURON objects.
                `is_subcomponent`  -- Whether to use the 'SUFFIX' tag or not.
                `ode_solver`       -- specifies the ODE solver to use
        """
        assert isinstance(prototype, Dynamics), \
            ("Provided prototype class '{}' is not a Dynamics object"
             .format(prototype))
        if isinstance(prototype, Kinetics):
            self.generate_kinetics(name, prototype, initial_state, src_dir,
                                   **kwargs)
        elif 'membrane_voltage' in kwargs:
            self.generate_point_process(
                name, prototype, initial_state, src_dir, **kwargs)
        else:
            self.generate_ion_channel(name, prototype, initial_state, src_dir,
                                      **kwargs)

    def generate_ion_channel(self, name, prototype, initial_state, src_dir,
                             **kwargs):
        # Render mod file
        self.generate_mod_file(name, 'main.tmpl', prototype, initial_state,
                               src_dir, kwargs)

    def generate_kinetics(self, name, prototype, initial_state, src_dir,
                          **kwargs):
        # Render mod file
        self.generate_mod_file(name, 'kinetics.tmpl', prototype, initial_state,
                               src_dir, kwargs)

    def generate_point_process(self, name, prototype, initial_state, src_dir,
                               **kwargs):
        add_tmpl_args = {'is_subcomponent': False}
        template_args = copy(kwargs)
        template_args.update(add_tmpl_args)
        # Render mod file
        self.generate_mod_file(name, 'main.tmpl', prototype, initial_state,
                               src_dir, template_args)

    def generate_mod_file(self, name, template, prototype, initial_state,
                          src_dir, template_args):
        tmpl_args = {
            'component_name': name,
            'componentclass': prototype.component_class,
            'prototype': prototype,
            'initial_state': initial_state,
            'version': pype9.version, 'src_dir': src_dir,
            'timestamp': datetime.now().strftime('%a %d %b %y %I:%M:%S%p'),
            'unit_conversion': self.unit_conversion,
            'ode_solver': self.ODE_SOLVER_DEFAULT,
            'external_ports': [],
            'is_subcomponent': True,
            # FIXME: weight_vars needs to be removed or implmented properly
            'weight_variables': []}
        tmpl_args.update(template_args)
        # Render mod file
        self.render_to_file(template, tmpl_args, name + '.mod', src_dir)

    @classmethod
    def transform(cls, prototype, **kwargs):
        """
        Copy the component class to alter it to match NEURON's current
        centric focus
        `membrane_voltage` -- the name of the state variable that represents
                              the membrane voltage
        `membrane_voltage` -- the name of the capcitance that represents
                              the membrane capacitance
        """
        # ---------------------------------------------------------------------
        # Clone original component class and properties
        # ---------------------------------------------------------------------
        orig = prototype.component_class
        # Clone component class before transforming
        trans = copy(orig)
        # Clone properties for transformed component
        props = [copy(p) for p in prototype.properties]
        # ---------------------------------------------------------------------
        # Remove the membrane voltage
        # ---------------------------------------------------------------------
        # Get or guess the location of the membrane voltage
        orig_v = cls._get_member_from_kwargs_or_guess_via_dimension(
            'membrane_voltage', 'state_variables', un.voltage, orig, kwargs)
        # Map voltage to hard-coded 'v' symbol
        if orig_v.name != 'v':
            trans.rename_symbol(orig_v.name, 'v')
            v = trans.state_variable('v')
            orig_v.annotations[PYPE9_NS][TRANSFORM_NS]['target'] = v
            v.annotations[PYPE9_NS][TRANSFORM_NS]['source'] = orig_v
        else:
            v = trans.state_variable('v')
        # Replace voltage state-variable with analog receive port
        trans.remove(v)
        v_port = AnalogReceivePort(v.name, dimension=un.voltage)
        orig_v.annotations[PYPE9_NS][TRANSFORM_NS] = v_port
        trans.add(v_port)
        # Remove associated analog send port if present
        try:
            trans.remove(trans.analog_send_port('v'))
        except KeyError:
            pass
        # ---------------------------------------------------------------------
        # Insert membrane capacitance if not present
        # ---------------------------------------------------------------------
        # Get or guess the location of the membrane capacitance
        try:
            orig_cm = cls._get_member_from_kwargs_or_guess_via_dimension(
                'membrane_capactiance', 'parameters', un.specificCapacitance,
                orig, kwargs)
            cm_prop = props(orig_cm.name)
            cm = trans.parameter(orig_cm.name)
        except Pype9NoElementWithMatchingDimensionException:
            # Add capacitance parameter if it isn't present
            cm_prop = Property(name='cm_', value=1.0, units=un.uF_per_cm2)
            cm = Parameter('cm_', dimension=un.specificCapacitance)
            cm.annotations[PYPE9_NS][TRANSFORM_NS]['source'] = None
            props.append(cm_prop)
            trans.add(cm)
        # ---------------------------------------------------------------------
        # Add current to component
        # ---------------------------------------------------------------------
        # Get the voltage time derivatives from each regime (must be constant
        # as there is no OutputAnalog in the spec see )
        dvdt = next(trans.regimes).time_derivative(v.name)
        for regime in trans.regimes:
            if regime.time_derivative(v.name) != dvdt:
                raise Pype9RuntimeError(
                    "Cannot convert to current centric as the voltage time for"
                    " derivative equation changes between regimes")
            regime.remove(regime.time_derivative(v.name))
        # Add alias expression for current
        i = Alias('i_', rhs=dvdt.rhs * cm)
        i.annotations[PYPE9_NS][TRANSFORM_NS]['source'] = (dvdt, cm), dvdt * cm
        dvdt.annotations[PYPE9_NS][TRANSFORM_NS]['target'] = (i, cm), i / cm
        trans.add(i)
        # Add analog send port for current
        i_port = AnalogSendPort('i_', dimension=un.currentDensity)
        i_port.annotations[PYPE9_NS][ION_SPECIES_NS] = 'non_specific'
        trans.add(i_port)
        # ---------------------------------------------------------------------
        # Validate the transformed component class and construct prototype
        # ---------------------------------------------------------------------
        trans.validate()
        # Retun a prototype of the transformed class
        return prototype.__class__(
            Definition(trans, Document(trans)), props.itervalues())

    def configure_build_files(self, name, src_dir, compile_dir, install_dir):
        pass

    def compile_source_files(self, compile_dir, component_name, verbose):
        """
        Builds all NMODL files in a directory
        `src_dir`     -- The path of the directory to build
        `build_mode`  -- Can be one of either, 'lazy', 'super_lazy',
                           'require', 'force', or 'build_only'. 'lazy' doesn't
                           run nrnivmodl if the library is found, 'require',
                           requires that the library is found otherwise throws
                           an exception (useful on clusters that require
                           precompilation before parallelisation where the
                           error message could otherwise be confusing), 'force'
                           removes existing library if found and recompiles,
                           and 'build_only' removes existing library if found,
                           recompile and then exit
        `verbose`     -- Prints out verbose debugging messages
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
                "directory '{}':\n\n{}".format(component_name, compile_dir, e))

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
