import numpy as np

from hls4ml.model.optimizer import OptimizerPass

from hls4ml.model.hls_model import Layer, register_layer
from hls4ml.templates import templates

class Clone(Layer):
    ''' Inserted after the layer whose output is used more than once.'''

    def initialize(self):
        inp = self.get_input_variable()
        self.add_output_variable(inp.shape, inp.dim_names, out_name=self.outputs[0], var_name='layer{index}_cpy1')
        self.add_output_variable(inp.shape, inp.dim_names, out_name=self.outputs[1], var_name='layer{index}_cpy2')

    def function_cpp(self):
        params = self._default_function_params()
        params['size'] = self.get_attr('size')
        params['output1'] = self.variables[self.outputs[0]].name
        params['output2'] = self.variables[self.outputs[1]].name
        return [self._function_template.format(**params)]

    def config_cpp(self):
        return None

clone_function_template = 'nnet::clone_stream<{input_t}, {output_t}, {size}>({input}, {output1}, {output2});'
clone_include_list = ['nnet_utils/nnet_stream.h']

class CloneThree(Layer):
    ''' Inserted after the layer whose output is used more than twice.'''

    def initialize(self):
        inp = self.get_input_variable()
        self.add_output_variable(inp.shape, inp.dim_names, out_name=self.outputs[0], var_name='layer{index}_cpy1')
        self.add_output_variable(inp.shape, inp.dim_names, out_name=self.outputs[1], var_name='layer{index}_cpy2')
        self.add_output_variable(inp.shape, inp.dim_names, out_name=self.outputs[2], var_name='layer{index}_cpy3')

    def function_cpp(self):
        params = self._default_function_params()
        params['size'] = self.get_attr('size')
        params['output1'] = self.variables[self.outputs[0]].name
        params['output2'] = self.variables[self.outputs[1]].name
        params['output3'] = self.variables[self.outputs[2]].name
        return [self._function_template.format(**params)]

    def config_cpp(self):
        return None

clonethree_function_template = 'nnet::clone_stream<{input_t}, {output_t}, {size}>({input}, {output1}, {output2}, {output3});'
clonethree_include_list = ['nnet_utils/nnet_stream.h']

# Register the layer types to the layer map
register_layer('Clone', Clone)
register_layer('CloneThree', CloneThree)

# Register the templates for config and function
for backend in ['Vivado', 'VivadoAccelerator']:
    templates.get_backend(backend).register_templates('Clone', clone_function_template, None, clone_include_list)
    templates.get_backend(backend).register_templates('CloneThree', clonethree_function_template, None, clonethree_include_list)


class CloneOutput(OptimizerPass):
    ''' Clones streams that are used multiple times '''
    def match(self, node):
        # We may have already inserted the Clone layer
        if node.__class__.__name__ in ['Clone', 'CloneThree']:
            return False

        return True

    def transform(self, model, node):
        if model.config.backend.name not in ['Vivado', 'VivadoAccelerator'] or \
            model.config.get_config_value('IOType') != 'io_stream':
            return False

        output_map = {}
        for output in node.outputs:
            output_map[output] = []
            for layer in model.get_layers():
                for inp in layer.inputs:
                    if output == inp:
                        output_map[output].append(layer)

        transformed = False
        for output in node.outputs:
            if len(output_map[output]) > 1:
                if len(output_map[output]) > 3:
                    print('WARNING: Cloning output {} of {} ({}) more than 3 times not currently supported'.format(output, node.__class__.__name__, node.name))
                    return False
                out_var = node.get_output_variable(output)
                for i, layer in enumerate(output_map[output], 1):
                    attrs = {
                        'size' : np.prod(out_var.shape)
                    }
                    idx = layer.inputs.index(output)
                    layer.inputs[idx] = output + '_cpy' + str(i)
                if len(output_map[output]) == 3:
                    clone_layer = model.make_node('CloneThree', 'clone_' + node.name, attrs, [output], [output + '_cpy1', output + '_cpy2', output + '_cpy3'])
                else:
                    clone_layer = model.make_node('Clone', 'clone_' + node.name, attrs, [output], [output + '_cpy1', output + '_cpy2'])
                model.insert_node(clone_layer)
                transformed = True
        
        return transformed
