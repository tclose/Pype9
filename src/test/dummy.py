#!/usr/bin/env python
from pyNN.neuron import Population, setup, run, h
from pyNN.parameters import Sequence
from pyNN.neuron.standardmodels.cells import SpikeSourceArray, IF_cond_alpha
NUM_DUMMY_CELLS=900
NUM_CELLS=8100
setup(1, 1.5, 100)
spike_times = []
for i in xrange(NUM_CELLS):
    spike_times.append(Sequence([i]))
dummy_pop = Population(NUM_DUMMY_CELLS, IF_cond_alpha, {})
pop = Population(NUM_CELLS, SpikeSourceArray, {'spike_times': spike_times})
pop.record('spikes')
run(NUM_CELLS)
pop.write_data('output/spikes.pkl')
h.quit()
print "done"
