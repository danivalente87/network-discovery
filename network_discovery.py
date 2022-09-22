import sys
import logging
import traceback

from ncclient import manager
import xmltodict
from lxml import etree
from xml.etree import ElementTree as ET
from collections import defaultdict

#logging.basicConfig(level=logging.DEBUG)

hosts = {
    "P1": {
        "host": "localhost",
        "port": 12022,
        "username": "cisco",
        "password": "cisco",
        "device_type": "1.1.1.1"
    },
    "P2": {
        "host": "localhost",
        "port": 13022,
        "username": "cisco",
        "password": "cisco",
        "device_type": "2.2.2.2"
    },
    "P3": {
        "host": "localhost",
        "port": 14022,
        "username": "cisco",
        "password": "cisco01",
        "device_type": "3.3.3.3"
    },
    "P4": {
        "host": "localhost",
        "port": 15022,
        "username": "cisco",
        "password": "cisco01",
        "device_type": "4.4.4.4"
    },
    "PE1": {
        "host": "localhost",
        "port": 10022,
        "username": "cisco",
        "password": "cisco",
        "device_type": "7.7.7.7"
    },
    "P5": {
        "host": "localhost",
        "port": 16022,
        "username": "cisco",
        "password": "cisco",
        "device_type": "5.5.5.5"
    },
    "P6": {
        "host": "localhost",
        "port": 17022,
        "username": "cisco",
        "password": "cisco",
        "device_type": "6.6.6.6"
    }
}

def xr_connect(host, port, username, password, device_type):
    return manager.connect(host=host,
                           port=port,
                           username=username,
                           password=password,
                           device_params={'name': 'iosxr'},
                           timeout=360
            )


def get_bgp_asn(conn):
    bgp_asn = '''

    <bgp xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-bgp-cfg'>
    <instance>
        <instance-as>
        <four-byte-as>
        <as></as>
        </four-byte-as>
        </instance-as>
    </instance>
    </bgp>
    '''
    print('Getting BGP ASN configuration ...\n')
    output = conn.get(filter=('subtree', bgp_asn))
    return xmltodict.parse(output.xml)['rpc-reply']['data']['bgp']['instance']['instance-as']['four-byte-as']['as']

def get_ospf_id(conn):
    ospf_config = '''

    <ospf xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-ospf-cfg'>
    <processes>
        <process>
        </process>
    </processes>
    </ospf>
    '''
    print('Getting OSPF CONFIG ...\n')
    default_vrf_ospf = []
    non_default_vrf_ospf = []
    output = conn.get(filter=('subtree', ospf_config))
    output = xmltodict.parse(output.xml)['rpc-reply']['data']['ospf']['processes']['process']
    if type(output) == list:   # NETCONF will return a dict if only one process and a list if > 1.
        for process in output:
            if 'vrfs' not in process:
                default_vrf_ospf.append(process['process-name'])
            else:
                non_default_vrf_ospf.append(process['process-name'])
        return default_vrf_ospf, non_default_vrf_ospf
    else:
        if 'vrfs' not in output:
            default_vrf_ospf.append(output['process-name'])
        else:
            non_default_vrf_ospf.append(output['process-name'])
        return default_vrf_ospf, non_default_vrf_ospf

def get_linecards(conn):
    linecards = '''

    <platform xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-plat-chas-invmgr-ng-oper'>
    </platform>
    '''
    show_platform = {}

    print('Getting LINECARD configuration ...\n')
    output = conn.get(filter=('subtree', linecards))
    output = xmltodict.parse(output.xml)['rpc-reply']['data']['platform']['racks']['rack']['slots']['slot']

    return output


def get_core_interfaces(conn):
    # using interfaces with mpls ldp discovery items.
    mpls_ldp_enabled = '''

    <mpls-ldp xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-mpls-ldp-oper'>
    <global>
    <active>
    <default-vrf>
    <afs>
    <af>
    <discovery>
    <link-hellos>
    <link-hello>
    </link-hello>
    </link-hellos>
    </discovery>
    </af>
    </afs>
    </default-vrf>
    </active>
    </global>
    </mpls-ldp>
    '''
    print("Gathering CORE interaces ... \n")
    core_interface_list = []
    core_neighbor_list = []
    core_per_neighbor = defaultdict(list)
    core_per_neighbor_dict = {}

    try:
        output = conn.get(filter=('subtree', mpls_ldp_enabled))
        output = xmltodict.parse(output.xml)['rpc-reply']['data']['mpls-ldp']['global']['active']['default-vrf']['afs']['af']['discovery']['link-hellos']['link-hello']
    except Exception as e:
        print(f"Exception : {e}")
        return ''


    if type(output) == list:
        # means that there are more than 1 LDP Interface with hello received
        for interface in output:
            if 'hello-information' in interface:
                core_interface_list.append(interface['interface-name'])
                core_neighbor_list.append(interface['hello-information']['neighbor-transport-address']['ipv4'])
    else:
        if 'hello-information' in output:
            core_interface_list.append(output['interface-name'])
            core_neighbor_list.append(output['hello-information']['neighbor-transport-address']['ipv4'])

    for key, value in zip(core_neighbor_list, core_interface_list):
        core_per_neighbor[key].append(value)

    core_per_neighbor_dict = dict(core_per_neighbor)

    #return core_interface_list, core_neighbor_list, core_per_neighbor_dict
    return core_per_neighbor_dict

def get_member_intf(conn):
    member_interfaces = '''

    <bundles xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-bundlemgr-oper'>
    <bundles>
    <bundle>
    <members>
    </members>
    </bundle>
    </bundles>
    </bundles>
    '''
    bundle_list = {}
    member_list = []
    print("Gathering Member information ... \n")
    try:
        output = conn.get(filter=('subtree', member_interfaces))
        output = xmltodict.parse(output.xml)['rpc-reply']['data']['bundles']['bundles']['bundle']
    except Exception as e:
        print(f'Error: {e} ')
        return ' '

    print(output)
    if type(output) == list:          # if multiple bundles
        for bundle in output:
            member_list = []
            for item in bundle['members'].values():
                if type(item) == list:
                    for member in item:
                        member_list.append(member['member-interface'])
                else:
                    member_list.append(item['member-interface'])
            bundle_list[bundle['bundle-interface']] = member_list
    else:                               # if only one bundle -
        member_list = []
        for item in output['members'].values():
            if type(item) == list:
                for member in item:
                    member_list.append(member['member-interface'])
            else:
                member_list.append(item['member-interface'])
        bundle_list[output['bundle-interface']] = member_list

    return bundle_list


def find_hostnames(core_per_neighbor_dict):
        hostnames = {}
        if core_per_neighbor_dict == '':
            return ''
        for neighbor_ip in core_per_neighbor_dict.keys():
            hostnames[neighbor_ip] = "NULL"
            for device in hosts.keys():
                if neighbor_ip == hosts[device]['device_type']:
                    hostnames[neighbor_ip] = device

        return hostnames



def bgp_neighbors(conn):
    '''
    :param conn:
    :return: Dictionary with attributes
    '''


    bgp_rr = '''

    <bgp xmlns='http://cisco.com/ns/yang/Cisco-IOS-XR-ipv4-bgp-oper'>
    <instances>
            <instance>
                <instance-active>
                    <default-vrf>
                        <neighbors>
                            <neighbor>
                                <connection-state>bgp-st-estab</connection-state>
                            </neighbor>
                        </neighbors>
                    </default-vrf>
                </instance-active>
            </instance>
    </instances>
    </bgp>
    '''   # getting only neighbors with session established. to get all neighbors, remove filter

    bgp_neigh_dict = {}

    print('Getting BGP RR status ...\n')
    output = conn.get(filter=('subtree', bgp_rr))
    output = xmltodict.parse(output.xml)['rpc-reply']['data']['bgp']['instances']['instance']['instance-active']['default-vrf']['neighbors']['neighbor']

    if type(output) == list:
        for neighbor in output:
            bgp_neigh_dict[neighbor['neighbor-address']] = {}
            bgp_neigh_dict[neighbor['neighbor-address']]['prefixes'] = neighbor['af-data']['prefixes-accepted']
            bgp_neigh_dict[neighbor['neighbor-address']]['is-ibgp'] = True if neighbor['remote-as'] == neighbor['local-as'] else False
    else:
        bgp_neigh_dict[output['neighbor-address']] = {}
        bgp_neigh_dict[output['neighbor-address']]['prefixes'] = output['af-data']['prefixes-accepted']
        bgp_neigh_dict[output['neighbor-address']]['is-ibgp'] = True if output['remote-as'] == output['local-as'] else False

    return bgp_neigh_dict




for device in hosts.keys():
    try:
        conn = xr_connect(**hosts[device])
        f = open(f'/Users/dsiman/Documents/devnet/RESTCONF/DUT_{device}.txt', 'w')
        if conn.connected:

            f.write("\n+++++++++ BGP CONFIG ++++++++++++++++++++")
            f.write("\nBGP_ASN: " + get_bgp_asn(conn) + '\n\n')
            neighbor_dict = bgp_neighbors(conn)
            internal_bgp_list = []
            external_bgp_list =  []
            for nbr in neighbor_dict:
                if neighbor_dict[nbr]['is-ibgp']:
                    internal_bgp_list.append(nbr)
                else:
                    external_bgp_list.append(nbr)

            f.write('\nBGP Neighbors and Prefixes: ' + str(neighbor_dict) + '\n\n' )
            f.write("\nInternal BGP Neighbors: " + str(internal_bgp_list) + '\n\n')
            f.write(('\nExternal BGP Neighbors: ' + str(external_bgp_list) + '\n\n'))
            f.write("- - - - - " * 50)

            f.write("\n+++++++++ OSPF CONFIG ++++++++++++++++++++")
            default_vrf_ospf, non_default_vrf_ospf = get_ospf_id(conn)
            f.write("\nOSPF_GLOBAL: " + str(default_vrf_ospf) + "\n\n")
            f.write("\nOSPF_VRF: " + str(non_default_vrf_ospf) + "\n\n")
            f.write("- - - - - " * 50)

            f.write("\n+++++++++ INTERFACES ++++++++++++++++++++")
            core_per_neighbor_dict = get_core_interfaces(conn)
            neighbor_hostnames = find_hostnames(core_per_neighbor_dict)
            #core_interface_list , core_neighbor_list , core_per_neighbor_dict = get_core_interfaces(conn)
            f.write("\nBundles Members: " + str(get_member_intf(conn)) + '\n\n')
            f.write("\nCore interfaces per neighbor: " + str(core_per_neighbor_dict) + '\n\n')
            f.write("\nNeighbors Hostname : " + str(neighbor_hostnames) + "\n\n")
            f.write("- - - - - " * 50)

            f.write("\n+++++++++ LINECARDS ++++++++++++++++++++")
            f.write("\nLinecards: " + str(get_linecards(conn)) + '\n\n')
            f.write("- - - - - " * 50)







            # add a var log here to log the devices that were completed.
    except Exception as e:
        print(f'Execption: {e}')
        print(traceback.format_exc())
