from collections import OrderedDict
import oyaml as yaml
from src.data import *
from src.helpers import debug_yaml  # For debugging only
from src.helpers import prettyprint # For debugging only
import ipaddress
import sys

class Router(object):
    def __init__(self, data, router_name, template, subnet_list):
        self.data = data
        self.router_name = router_name
        self.template = template
        self.subnet_list = subnet_list
        self.subnet_count = len(self.data['properties']['networks'])
        self.initialize_router()

    def initialize_router(self):
        netname = self.add_net()
        self.add_router()
        self.add_router_interfaces()
        self.add_subnets(netname)

    def add_net(self):
        netname = str(self.router_name + '-net')
        self.template['resources'].update(OrderedDict({
            str(self.router_name + '-net'): {
                'type': 'OS::Neutron::Net',
                'properties': {
                    'name': netname
                }
            }
        }))
        return netname

    def get_allocated_subnets(self):
        return self.subnet_list

    def allocate_subnet(self):
        """Allocate an IP address range in CIDR format to a subnet"""
        if len(self.subnet_list) == 0:
            subnet = '192.168.1.0/24'
            self.subnet_list.append(subnet)
            return subnet
        else:
            subnet = self.subnet_list[::-1][0]
            ip = ipaddress.IPv4Network(subnet)[0]
            s = ipaddress.IPv4Address(ip) + 256
            return '{}{}'.format(s, '/24')

    def set_cidr(self, subnet):
        if self.data['properties']['networks'][subnet] is not None and 'cidr' in self.data['properties']['networks'][subnet].keys():
            try:
                cidr = str(self.data['properties']['networks'][subnet]['cidr'])
                cidr = ipaddress.IPv4Network(cidr)
                return str(cidr)
            except ValueError:
                print('Invalid CIDR range selected for subnet: ' + subnet)
                sys.exit(1)
        elif self.data['properties']['networks'][subnet] is None:
            return str(self.allocate_subnet())
    
    def set_gatewayIP(self, subnet, cidr):
        if self.data['properties']['networks'][subnet] is not None and 'gatewayIP' in self.data['properties']['networks'][subnet].keys():
            ip = str(self.data['properties']['networks'][subnet]['gatewayIP'])
            if ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(cidr):
                return ip
            else:
                print('The selected GatewayIP is not invalid')
                sys.exit(1)
        elif self.data['properties']['networks'][subnet] is None:
            ip = ipaddress.IPv4Network(cidr)[1]
            return str(ip)

    def set_dhcp_pools(self, cidr):
        """Sets the DHCP pool boundary"""
        start = str(ipaddress.IPv4Network(cidr)[50])
        end   = str(ipaddress.IPv4Network(cidr)[200])
        return start, end



    def add_subnets(self, netname):
        """Add subnet heat resources and parameters to the template"""
        for subnet in self.data['properties']['networks'].keys():
            subnet_resource = OrderedDict({
                subnet: {
                    'type': 'OS::Neutron::Subnet',
                    'properties': {
                        'name': subnet,
                        'network_id': { 
                            'get_resource': netname, 
                        },
                        'cidr': { 
                            'get_param': subnet + '_net_cidr'
                        },
                        'gateway_ip': { 
                            'get_param': subnet + '_net_gateway'
                        },
                        'allocation_pools': [{
                            'start': { 'get_param': subnet + '_net_pool_start' },
                            'end': { 'get_param': subnet + '_net_pool_end' }
                        }],
                    }
                }
            })
            self.template['resources'].update(subnet_resource)
            cidr = self.set_cidr(subnet)
            gw = self.set_gatewayIP(subnet, cidr)
            self.template['parameters'].update(OrderedDict({
                subnet + '_net_cidr': {
                    'type': 'string',
                    'default': cidr
                }}))
            self.template['parameters'].update(OrderedDict({
                subnet + '_net_gateway': {
                    'type': 'string',
                    'default': gw
                }}))
            self.template['parameters'].update(OrderedDict({
                subnet + '_net_pool_start': {
                    'type': 'string',
                    'default': self.set_dhcp_pools(cidr)[0]
                }}))
            self.template['parameters'].update(OrderedDict({
                subnet + '_net_pool_end': {
                    'type': 'string',
                    'default': self.set_dhcp_pools(cidr)[1]
                }}))

    def add_router(self):
        """Add a router heat template resource to the template"""
        router = OrderedDict({self.router_name: {
            'type': 'OS::Neutron::Router',
            'properties': {
                'name': self.router_name,
                'external_gateway_info': {
                    'network': { 'get_param': 'public_net' }
                }
            }
        }})
        self.template['resources'].update(router)

    def add_router_interfaces(self):
        """Adds the router's interfaces to the heat template"""
        for subnet_name in self.data['properties']['networks'].keys():
            interface = OrderedDict({
                str(self.router_name + '_interface_' + subnet_name): {
                    'type': 'OS::Neutron::RouterInterface',
                    'properties': {
                        'router_id': { 'get_resource': self.router_name },
                        'subnet_id': { 'get_resource': subnet_name  }
                    }   
                }
            })
            self.template['resources'].update(interface)