from collections import OrderedDict
import oyaml as yaml
from src.data import *
import sys

from src.helpers import debug_yaml  # For debugging only
from src.helpers import prettyprint # For debugging only

class Node(object):
    def __init__(self, data, node_name, template):
        self.data = data
        self.node_name = node_name
        self.template = template
        self.subnet_count = self.count_subnets()
        self.initialize_node()

    def count_subnets(self):
        if not 'networks' in self.data['properties'].keys():
            return 0
        elif self.data['properties']['networks'] == None:
            return 0
        else:
            return len(self.data['properties']['networks'])

    def get_node_ports(self):
        subnet_list = []
        for router in self.data['properties']['networks'].keys():
            for k in self.data['properties']['networks'][router]['subnet'].split(','):
                subnet = str(k).strip(' ')
                subnet_list.append((router, subnet))
        for port_number, subnet_name in zip(range(0, len(subnet_list)), subnet_list):
            yield (port_number, subnet_name[0], subnet_name[1])

    def initialize_node(self):
        self.add_node()
        if 'networks' in self.data['properties'].keys() and self.data['properties']['networks'] is not None:
            self.add_node_ports()
        self.add_security_group()

    def set_flavor(self):
        if 'flavor' not in self.data['properties'].keys():
            return 'm1.small'
        elif self.data['properties']['flavor'].lower() not in flavor_list:
            print('Invalid flavor selected')
            sys.exit(1)
        else:
            return str(self.data['properties']['flavor'])
    
    def set_operating_system(self):
        if 'os' not in self.data['properties'].keys():
            return 'Ubuntu Server 18.04 LTS (Bionic Beaver) amd64'      # Default OS unless specified
        elif self.check_os_family() is None:
            print('Invalid operating system selected')
            sys.exit(1)
        else:
            return str(self.data['properties']['os'])

    def check_os_family(self):
        os = str(self.data['properties']['os']).lower()
        for image in windows_image_list:
            if os in str(image).lower():
                return 'windows'
        for i in linux_image_list:
            if os in str(i).lower():
                return 'linux'
        return None

    def add_node_ports(self):
        
        for port_number, router, subnet in self.get_node_ports():
            a = self.data['properties']['networks'].keys()
            #print(a)
            port_name = str(self.node_name + '_port' + str(port_number))
            port = OrderedDict({
            port_name: {
                'type': 'OS::Neutron::Port',
                'properties': {
                    'network': { 'get_resource': str(router + '-net') },
                    'security_groups': [{ 'get_resource': self.node_name + '_security_group_' + subnet }],
                    'fixed_ips': [{
                        'subnet_id': { 'get_resource': subnet }
                    }]
                }}
            })
            self.template['resources'].update(port)

    def add_node(self):
        port_list = []
        for portnumber in range(0, self.subnet_count):
            port_list.append(OrderedDict({
                'port': { 'get_resource': self.node_name + '_port' + str(portnumber) }
            }))
        # Node resource
        node = OrderedDict({
            self.node_name: {
                'type': 'OS::Nova::Server',
               # 'depends on': 'management',
                'properties': {
                    'name': { 'get_param': self.node_name + '_server_name' },
                    'image': { 'get_param': self.node_name + '_image' },
                    'flavor': { 'get_param': self.node_name + '_flavor' },
                    'key_name': { 'get_param': 'key_name' },                # This should be made dynamic at some point
                    'networks': port_list,
                    #'puppet_master_ip': 
                    'user_data_format': 'RAW',
                    'user_data': 
                        self.add_software_config() # Fix this function
                }
            }
        })
        self.template['resources'].update(node)

        # Heat parameters related to Node
        self.template['parameters'].update(OrderedDict({
            str(self.node_name + '_server_name'): {
                'type': 'string',
                'default': str(self.node_name)
            }
        }))
        self.template['parameters'].update(OrderedDict({
            str(self.node_name + '_image'): {
                'type': 'string',
                'default': str(self.set_operating_system())
            }
        }))
        self.template['parameters'].update(OrderedDict({
            str(self.node_name + '_flavor'): {
                'type': 'string',
                'default': str(self.set_flavor())
            }
        }))
        self.template['parameters'].update(OrderedDict({
            'key_name': {
                'type': 'string'
            }
        }))

    def add_floating_ip(self):
        """Associates a node with the node in the template"""
        for router in self.data['properties']['networks'][router].keys():
            if 'public_ip' in self.data['properties']['networks'][router].keys() or self.data['properties']['networks'][router]['public_ip'] == 'yes':
                self.template['resources'].update(OrderedDict({
                    self.node_name + '_floating_ip': {
                        'type': 'OS::Neutron::FloatingIP',
                        'properties': {
                            'floating_network_id': { 'get_param': 'public_net' },
                            'port_id': { 'get_resource': self.node_name + '_port0' } 
                        }
                    }
                }))
                
    def create_portsecurity_rule(self, port, protocol):
        """Creates a security rule"""
        return OrderedDict({
            'remote_ip_prefix': '0.0.0.0/0',
            'protocol': protocol,
            'port_range_min': port,
            'port_range_max': port
        })

    def add_security_group(self):
        """Adds a security group resource to the template"""
        # ICMP is always allowed.
        rule_list = [
            OrderedDict({
                'remote_ip_prefix': '0.0.0.0/0',
                'protocol': 'icmp'
            })]

        for router in self.data['properties']['networks']:
            subnet = self.data['properties']['networks'][router]['subnet']
            resource_name = str(self.node_name + '_security_group_' + subnet)

            if 'port_security' not in self.data['properties']['networks'][router].keys():
                rule_list.append(self.create_portsecurity_rule(22, 'tcp'))
                continue
             
            if 'tcp' in self.data['properties']['networks'][router]['port_security'].keys():
                # All servers must have SSH even if not specified
                if 22 not in self.data['properties']['networks'][router]['port_security']['tcp']:
                    rule_list.append(self.create_portsecurity_rule(22, 'tcp'))

                for tcp_port in self.data['properties']['networks'][router]['port_security']['tcp']:
                    rule_list.append(self.create_portsecurity_rule(tcp_port, 'tcp'))

            else:
                rule_list.append(self.create_portsecurity_rule(22, 'tcp'))

            if 'udp' in self.data['properties']['networks'][router]['port_security'].keys(): 
                for udp_port in self.data['properties']['networks'][router]['port_security']['udp']:
                    rule_list.append(self.create_portsecurity_rule(udp_port, 'udp'))

            # Security group Heat resource
        secgrp = OrderedDict({
            resource_name: {
            'type': 'OS::Neutron::SecurityGroup',
            'properties': {
                'rules': rule_list
            }
        }})
        self.template['resources'].update(secgrp)

    def add_software_config(self): # It should be possible to select which files are used. Need to fix this.
        config = OrderedDict({
                'str_replace': {
                    'template': { 'get_file': 'lib/testing/foo.sh' },
                    'params': {
                        '__puppet_master_ip__': { 'get_attr': ['management', 'puppet_master_ip']}
                    }
                }
        })
      #  self.template['parameters'].update(OrderedDict({
      #      'puppet_master_ip': {
      #          'type': 'string'
      #      }
      #  }))
        return config