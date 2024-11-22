#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import required libraries
# Version 4.0
# Date 11/22/2024

# This file is for router type B4A, B4B, B4C, B4S and B4E

import pandas as pd
import os
import re
import sys
import subprocess
import requests
import hashlib
import logging
from datetime import datetime
from itertools import islice


# In[2]:


# Check version from Github
GITHUB_FILE_URL = "https://raw.githubusercontent.com/pranav-kaushal/Nokia/refs/heads/main/Hub-Spoke/HubSpoke_121to135LLD.py"
cwd = os.getcwd()
LOCAL_FILE_PATH  = os.path.join(cwd, "HubSpoke_121to135LLD.py") # Path for the current script file
print(cwd)
def get_remote_file_content(url, timeout=3):
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return response.content
        else:
            print(f"Failed to retrieve file. Status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def get_file_hash(content):
    return hashlib.md5(content).hexdigest()

def check_for_update():
    new_content = get_remote_file_content(GITHUB_FILE_URL)
    if not new_content:
        return False  # No update due to a fetch issue
    with open(LOCAL_FILE_PATH, "rb") as f:
        current_content = f.read()
    if get_file_hash(new_content) != get_file_hash(current_content):
        print("Update found! Updating script...")
        with open(LOCAL_FILE_PATH, "wb") as f:
            f.write(new_content)
        return True
    else:
        print("No update found.")
        return False

def restart_script():
    print("Restarting script...")
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit()  # Close the current script


# In[3]:


def scan_file():
    global my_files
    global cwd
    my_files = []
    cwd = os.getcwd() # check for the file in current directory
    file_path = os.listdir(cwd) # list the files
    for i in file_path:
        if '.cfg' in i or '.log' in i: # Chage this to .txt, or .cfg or .log based on your files.
            my_files.append(i)
    return (my_files, cwd)


# In[4]:


# Create alist of path for all the scanned files above.
def all_files():
    scan_file()
    global path
    path = []
    for i in range(len(my_files)):
        path.append(cwd+"/"+my_files[i])
    return path


# In[5]:


# Read the contents and extract the file name
def create_pd():
    # global variables to be used by other functions.
    global name, my_file_pd, router_type, ecmp_value , system_ip

    my_file_pd = pd.read_fwf(items, index_col=False, header=None,sep = ' ' )
    my_file_pd = my_file_pd.rename(columns = {0 : "config"})
    # Get site name
    site_name = my_file_pd.index[my_file_pd['config'].str.contains("name")]
    name = my_file_pd['config'][site_name[0]]
    name = name[6:-1].strip('"')
    
    # Search for rows containing 7705, 7750, or 7250
    search_terms = ['7705', '7250', '7750']
    for line in my_file_pd['config']:
        match = re.search(r'(7705|7250)', line)
        if match:
            router_type = match.group()
            #print(router_type)
        #Check for ecmp on IXRE B4C
    try:
        ecmp = my_file_pd['config'].index[my_file_pd['config'].str.contains(r'ecmp \d{1}', regex=True)] # 1 nos in ecmp
        ecmp = my_file_pd['config'][ecmp[0]]
        ecmp_value = ecmp.split()
        #print(ecmp_value[1])
    except IndexError:
        print("#-------------------#")
    
    try:
        sys_row = my_file_pd.index[my_file_pd['config'].str.contains('interface "system"', regex=False)].tolist()

        if sys_row:
            # The next row (IP address) is sys_row + 1
            next_row = sys_row[0] + 1
            address_row = my_file_pd['config'].iloc[next_row]
            
            # Use regex to extract the IP address and remove the /32
            match = re.search(r'address\s+(\d+\.\d+\.\d+\.\d+)/32', address_row)
            
            if match:
                system_ip = match.group(1)
    except IndexError:
        print("No system interface found")


# In[6]:


def get_bof(data):
    global bof_address_ip, static_next_hop
    bof_address_ip = None
    static_next_hop = None
    
    try:
        group_start_idx = data[data['config'].str.contains('BOF \(Memory\)')].index[0]
        group_end_idx = data[data['config'].str.contains('persist')].index[0]
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('address') or line.startswith('eth-mgmt-address'):
                bof_address_ip = line.split()[1]
            if line.startswith('static-route') or line.startswith('eth-mgmt-route') and static_next_hop is None:
                static_next_hop = line.split('next-hop')[1].strip()
                break  # Just the first static
    except IndexError:
        print("No BOF address or static route found. Please check the config manually")
    
    #return bof_address_ip, static_next_hop
def bof_data():
    global static_route_new_1, static_route_new_2, static_route_new_3, old_statics
    get_bof(my_file_pd)
    ## Create new static routes
    static_route_new_1 = "/bof static-route 2001:4888::/32 next-hop " + static_next_hop
    static_route_new_2 = "/bof static-route 2600::/16 next-hop " + static_next_hop
    static_route_new_3 = "/bof static-route 2607::/16 next-hop " + static_next_hop
    
    ## Remove of old static routes
    combined ='next-hop ' + static_next_hop
    # Get old static routes from config file based on gw from vpls400 and next-hop keyword
    #old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(combined)]
    if combined[-2:] == "::":
        comb = 'next-hop ' + static_next_hop[0:-2] #+ ":0:0"
        old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(comb, flags=re.I)]
    else:
        old_statics = my_file_pd['config'].index[my_file_pd['config'].str.contains(combined)]

def create_bof(old_statics):
    print('')
    print('#--------------------------------------------------')
    print('#System Name: {}"'.format(name))
    print('#--------------------------------------------------')
    print('########### Adding the New Static Routes ############')
    print('')
    print(static_route_new_1)
    print(static_route_new_2)
    print(static_route_new_3)
    if '7705' in router_type:
        print('/bof speed 100')
    elif 'B4B' in name:
        print('')
    else:
        print('/bof speed 1000')
    print('')
    print('')
    print('#--------------------------------------------------')
    print('########### Removing Old Static Routes ############')
    print('#--------------------------------------------------')
    print('/show bof')
    print('')
    for rts in old_statics:
        routes = my_file_pd['config'][rts]
        routes = re.sub(r' {4,}', ' ', routes)
        print("/bof no", routes)



def create_bof_b4e(old_statics):
    print('')
    print('#--------------------------------------------------')
    print('#System Name: {}"'.format(name))
    print('#--------------------------------------------------')
    print('########### Adding the New Static Routes ############')
    print('')
    print('/bof eth-mgmt-route 2001:4888::/32 next-hop {}'.format(static_next_hop))
    print('/bof eth-mgmt-route 2600::/16 next-hop {}'.format(static_next_hop))
    print('/bof eth-mgmt-route 2607::/16 next-hop {}'.format(static_next_hop))
    #print('/bof speed 1000')
    print('')
    print('')
    print('#--------------------------------------------------')
    print('########### Removing Old Static Routes ############')
    print('#--------------------------------------------------')
    print('/show bof')
    print('')
    for rts in old_statics:
        routes = my_file_pd['config'][rts]
        routes = re.sub(r' {4,}', ' ', routes)
        print("/bof no", routes)


# In[ ]:





# In[7]:


# Get the interfaces for which the metric has to be changed.
def metric_int_b4a(data):
    global met_int_b4c, met_int_b4b, met_int_b4s
    met_int_b4b = {}
    met_int_b4c = {}
    met_int_b4s= {}
    
    try:
        # Find the start of search keywordac
        group_start_idx = data[data['config'].str.fullmatch('router Base')].index[0] 
        group_end_idx = data[data['config'].str.match('echo "Service')].index[0]
        
        # Loop through the subsequent lines to find neighbors and descriptions
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        interface_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B4B' in description:  # Check if description does contain "B4B 300"
                    met_int_b4b[interface_desc] = description
                if 'B4C' in description:  # Check if description does contain "B4C 1000000"
                    met_int_b4c[interface_desc] = description
                if 'B4S' in description:  # Check if description does contain "B4C 1000000"
                    met_int_b4s[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("No B4C/B4B interface was found, Please check the config manually")

    #return metric_interface

def metric_interface_b4a(): # Interface output 
    metric_int_b4a(my_file_pd)

    if ecmp_value[1] == '4':
        print('')
    else:
        print('#---------------------------------------------------------#')        
        print('######-----       Change ecmp metric        -------######')
        print('#---------------------------------------------------------#')
        print("# The router has ecmp value other than 4 , please change it to ecmp 4 for B4A")
        print('/configure router ecmp 4')
    print('#---------------------------------------------------------#')        
    print('######-----  Change ISIS interface metric   -------######')
    print('#---------------------------------------------------------#')
    print('')
    print('/configure router isis 5 overload-on-boot timeout 180')
    print('')
    for interface_desc, description in met_int_b4c.items():
        print('/configure router isis 5 interface {} level 1 metric 1000000'.format(interface_desc))
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type fp'.format(interface_desc))
    for interface_desc, description in met_int_b4s.items():
        print('/configure router isis 5 interface {} level 1 metric 300'.format(interface_desc))
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type fp'.format(interface_desc))
    for interface_desc, description in met_int_b4b.items():
        print('/configure router isis 5 interface {} level 1 metric 300'.format(interface_desc))
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type fp'.format(interface_desc))
    


# In[8]:


def metric_int_b4b(data):
    global metric_b4a, metric_b40, metric_b4s
    
    metric_b40 = {}
    metric_b4a = {}
    metric_b4s = {}
    try:
        # Find the start of search keyword
        group_start_idx = data[data['config'].str.contains('echo "Router')].index[0] 
        group_end_idx = data[data['config'].str.contains('echo "MPLS')].index[0]
        
        # Loop through the subsequent lines to find neighbors and descriptions
        in_neighbor_block = False
        interface_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' in description:
                    metric_b40[interface_desc] = description
                if 'B4A' in description or 'B4B' in description:
                    metric_b4a[interface_desc] = description
                if 'B4S' in description:
                    metric_b4s[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("No B40/B4C interface was found, Please check the config manually")


def print_metric_interface_b4b():  # Interface output 
    metric_int_b4b(my_file_pd)
    print('#---------------------------------------------------------#')        
    print('######-----       Change ecmp metric        -------######')
    print('#---------------------------------------------------------#')
    if ecmp_value[1] != 16:
        print('#--------------------------------------------------')
        print("# Please change it to ecmp 16 if its not 16")
        print('#--------------------------------------------------')
        print('/configure router ecmp 16')
    print('/configure service vprn 1 ecmp 32')
    print('/configure service vprn 4 ecmp 32')
    # Hard code B4B only to 32 for vprn 4 and 1
    # B4A, B4C vprn 1 and vprn 4 ecmp is 4, B4B is 32 for vprn 1 and 4.
    # B4A, B4C router ecmp 4, B4B is 16.
    # B40 metric 1000000, B4A and B4B 300, B4S 150
    print('---------------------------------------------------------')        
    print('######-----  Change ISIS interface metric   -------######')
    print('---------------------------------------------------------')
    print('')
    print('/configure router isis 5 overload-on-boot timeout 180')
    print('')
    for interface_desc, description in metric_b40.items():
        print('/configure router isis 5 interface {} level 1 metric 1000000'.format(interface_desc))
        print('')
    for interface_desc, description in metric_b4a.items():
        print('/configure router isis 5 interface {} level 1 metric 300'.format(interface_desc))
        print('')
    for interface_desc, description in metric_b4s.items():
        print('/configure router isis 5 interface {} level 1 metric 150'.format(interface_desc))
        print('')
    print('---------------------------------------------------------')        
    print('######-----  Change interface BFD and Filter   -------######')
    print('---------------------------------------------------------')
    # Add the filter to B40 interface on B4B
    for interface_desc, description in metric_b40.items():
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type cpm-np'.format(interface_desc))
        print('/configure router interface {} ingress filter ip 10005'.format(interface_desc))
        print('')
    for interface_desc, description in metric_b4a.items():
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type cpm-np'.format(interface_desc))
        print('')
    for interface_desc, description in metric_b4s.items():
        print('/configure router interface {} bfd 50 receive 50 multiplier 5 type cpm-np'.format(interface_desc))
        print('')


# In[9]:


# Add ip filter on B4B
# B4B-01 first ip is B4B-01, B4B-02
# B4B-02 first ip is B4B-02, B4B-01
def increment_last_digit(ip):
    new_ip = re.sub(r'(\d+)$', lambda x: str(int(x.group(1)) + 1), ip)
    return new_ip

def decrement_last_digit(ip):
    new_ip = re.sub(r'(\d+)$', lambda x: str(int(x.group(1)) - 1), ip)
    return new_ip

def ip_filter_10005_b4b():
    filter_10005 = my_file_pd.index[my_file_pd['config'].str.contains('ip-filter 10005 name "ACL_BLOCK_BL_PEER"')]
    if '10005' not in filter_10005:
        print('---------------------------------------------------------')        
        print('######-----        IP Filter for B4B        -------######')
        print('---------------------------------------------------------')
        print('/configure filter')
        print('        ip-filter 10005 name "ACL_BLOCK_BL_PEER" create')
        print('            default-action forward')
        print('            description "Block MH-BFD and BGP from BL Peer"')
        print('            entry 20 create')
        print('                match protocol udp')
        if '-01' in name:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    dst-port eq 4784')
            print('                    src-ip {}/32'.format(increment_last_digit(system_ip)))
        else:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    dst-port eq 4784')
            print('                    src-ip {}/32'.format(decrement_last_digit(system_ip)))
        print('                exit')
        print('                action')
        print('                    drop')
        print('                exit')
        print('            exit')
        print('            entry 40 create')
        print('                match protocol tcp')
        if '-01' in name:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    dst-port eq 179')
            print('                    src-ip {}/32'.format(increment_last_digit(system_ip)))
        else:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    dst-port eq 179')
            print('                    src-ip {}/32'.format(decrement_last_digit(system_ip)))
        print('                exit')
        print('                action')
        print('                    drop')
        print('                exit')
        print('            exit')
        print('            entry 41 create')
        print('                match protocol tcp')
        if '-01' in name:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    src-ip {}/32'.format(increment_last_digit(system_ip)))
        else:
            print('                    dst-ip {}/32'.format(system_ip))
            print('                    src-ip {}/32'.format(decrement_last_digit(system_ip)))
        print('                    src-port eq 179')
        print('                exit')
        print('                action')
        print('                    drop')
        print('                exit')
        print('            exit')
        print('        exit')
        print('    exit all')


# In[10]:


#This code is for B4A
def port_bfd(data):
    global bfd_port_b4c, port_b4c_value , port_b4a_value
    port_b4c_value = None
    port_b4a_value = None
    bfd_port_b4c = {}
    bfd_port_b4a = {}
    try:
        # Find the start of search keyword
        group_start_idx = data[data['config'].str.contains('echo "Port ')].index[0] 
        group_end_idx = data[data['config'].str.contains('echo "System Sync-If')].index[0]
        
        # Loop through the subsequent lines to find ports and descriptions
        in_port_block = False
        port_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('port'):  # Identifying port lines
                in_port_block = True
                port_desc = line.split()[1]  # Extract the port ID
            elif line.startswith('description') and in_port_block:  # Check for description in the port block
                description = line.split(' ', 1)[1].strip('"')
                if 'B4C' in description:  # Check if description contains "B4C"
                    bfd_port_b4c[port_desc] = description
                if 'B4A' in description:  # Check if description contains "B4A"
                    bfd_port_b4c[port_desc] = description
            elif line == 'exit':  # Reset when block ends
                in_port_block = False
        for port_desc, description in bfd_port_b4c.items():
            port_des = [description]
            #if all ('1/1/' in item for item in port_des):
            if any('CIRCUIT' in item or 'circuit' in item for item in port_des): # if there is a circuit id in description its going to B40
                print('/configure router interface "system" bfd 250 receive 250 multiplier 3')
            else:  
                print('/configure router interface "system" bfd 100 receive 100 multiplier 3')
            if 'B4C' in description:
                port_b4c_value = 'B4C'
            if 'B4A' in description:
                port_b4a_value = 'B4A'
            break
        
    except IndexError:
        print("# No B4C port was found, please check the config manually")
    return port_b4c_value

#port_bfd(my_file_pd)
#print(bfd_port_b4c)
#print(description)


# In[11]:


def port_b4e(data):
    global mgmt_port_b4e
    mgmt_port_b4e = {}
    try:
        # Find the start of search keyword
        group_start_idx = data[data['config'].str.contains('echo "Port ')].index[0] 
        group_end_idx = data[data['config'].str.contains('echo "System Sync-If')].index[0]
        
        # Loop through the subsequent lines to find ports and descriptions
        in_port_block = False
        port_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('port'):  # Identifying port lines
                in_port_block = True
                port_desc = line.split()[1]  # Extract the port ID
            elif line.startswith('description') and in_port_block:  # Check for description in the port block
                description = line.split(' ', 1)[1].strip('"')
                if 'B4A' in description or 'B4B' in description or 'B4S' in description or 'SR1' in description or 'IXR' in description:
                    if 'MG' in description or 'Mg' in description or 'Manag' in description:
                        mgmt_port_b4e[port_desc] = description
            elif line == 'exit':  # Reset when block ends
                in_port_block = False
        print('#--------------------------------------------------------#')
        print('#--------   Only port speed and neg changes  ------------#')
        print('#--------------------------------------------------------#')
        print('#--------   Before you make changes please check port description for correct router  ------------#')
        for port_desc, description in mgmt_port_b4e.items():
            #print(port_desc, description)
            print('')
            print('#port {} '.format(description))
            print('/configure port {} ethernet speed 1000'.format(port_desc))
            print('/configure port {} ethernet auto negotiate'.format(port_desc))
            print('')
        
    except IndexError:
        print("# No MGMT port was found, please check the config manually")


# In[12]:


# Get the interfaces for which the metric has to be changed.
def metric_int_b4c(data):
    global metric_interface_b4ca, metric_interface_b4c
     
    metric_interface_b4ca = {}
    metric_interface_b4c = {}
    try:
        # Find the start of search keyword
        group_start_idx = data[data['config'].str.fullmatch('router Base')].index[0] 
        group_end_idx = data[data['config'].str.match('echo "Service')].index[0]
        
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        interface_desc = None
    
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B4C' in description:  # 
                    metric_interface_b4c[interface_desc] = description
                if 'B4A' in description:  # Check if description does contain "B4C 1000000"
                    metric_interface_b4ca[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("# No B4A/B4C interface was found, Please check the config manually")

    #return metric_interface
# check for type fp if its not type fp then change it to type fp
def interface_b4c(): # Interface output 
    
    global int_b4_value
    int_b4_value = None
    metric_int_b4c(my_file_pd)
    print('#--------------------------------------------------------#')
    print('######-----       Change ecmp metric        -------######')
    print('#--------------------------------------------------------#')
    print('')
    if ecmp_value[1] != 4:
        print('/configure router ecmp 4')
        print('/configure service vprn 1 ecmp 4')
        print('/configure service vprn 4 ecmp 4')
    print('#--------------------------------------------------------#')        
    print('######-----  Change ISIS interface metric   -------######')
    print('#--------------------------------------------------------#')
    print('')
    print('/configure router isis 5 overload-on-boot timeout 180')
    if '7250' in router_type:
        print('/configure port 1/1/24 ethernet speed 1000')
    print('')
    for interface_desc, description in metric_interface_b4ca.items():
        if '7705' in router_type:
            print('/configure router isis 5 interface {} level 1 metric 1000000'.format(interface_desc))
            print('/configure router interface {} bfd 50 receive 50 multiplier 5 type np'.format(interface_desc))
            print('#--------------------------------------------------------#')
        else:
            print('/configure router isis 5 interface {} level 1 metric 1000000'.format(interface_desc))
            print('/configure router interface {} bfd 50 receive 50 multiplier 5 type fp'.format(interface_desc))
            print('#--------------------------------------------------------#')
        if 'B4A' in description:
            int_b4_value = 'B4A'
    return int_b4_value
    
    


# In[13]:


# Get the interfaces for which the metric has to be changed.
def metric_int_b4s(data):
    global metric_interface_b4ab, interface_des
    metric_interface_b4ab = {} 
    interface_des = {}
    try:
        router_base_idx = data[data['config'].str.contains('router Base')].index[0]
        echo_service_idx = data[data['config'].str.contains('router-id ')].index[0]

        is_neighbor_block = False  # Use a boolean flag for block
        current_interface = None
        current_bfd = None

        for i in range(router_base_idx, echo_service_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('interface'):
                is_neighbor_block = True
                current_interface = line.split()[1]
                if 'INT' in line and 'system' not in line:
                    int_des = line
                current_bfd = None
            elif line.startswith('description') and is_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                interface_des[int_des] = description
                if 'B4A' in description or 'B4B' in description and 'INT' in description:
                    metric_interface_b4ab[current_interface] = description
                    
            elif line.startswith('bfd') and is_neighbor_block:
                current_bfd = line  # add bfd
                if current_interface and current_bfd:
                    metric_interface_b4ab[current_interface] = current_bfd  # Add BFD if present
            elif line == 'no shutdown':
                is_neighbor_block = False
                current_interface = None
                current_bfd = None
    except IndexError:
        print("# No B4A/B4B interface was found. Please check the config manually.")

    return metric_interface_b4ab, interface_des


def interface_qos_b4s():
    metric_int_b4s(my_file_pd)
    print('#------------------------------------------------------------------#')
    print('#---------------------       New QOS policy      ------------------#')
    print('#------------------------------------------------------------------#')
    print('/configure qos')
    print('        vlan-qos-policy "40013" create')
    print('            description "eNSE SR Network VLAN QOS Policy"')
    print('            stat-mode enqueued-with-discards')
    print('            queue "1" create')
    print('                percent-rate 100.00 cir 24.00')
    print('            exit')
    print('            queue "2" create')
    print('                percent-rate 100.00 cir 3.00')
    print('            exit')
    print('            queue "3" create')
    print('                percent-rate 100.00 cir 1.00')
    print('            exit')
    print('            queue "4" create')
    print('                percent-rate 100.00 cir 3.00')
    print('            exit')
    print('            queue "5" create')
    print('                percent-rate 100.00 cir 8.00')
    print('            exit')
    print('            queue "6" create')
    print('                percent-rate 100.00 cir 55.00')
    print('            exit')
    print('            queue "7" create')
    print('                percent-rate 100.00 cir 5.00')
    print('                queue-type expedite-lo')
    print('                exit')
    print('            exit')
    print('            queue "8" create')
    print('                percent-rate 100.00 cir 1.00')
    print('            exit')
    print('        exit')
    print('exit all')
    print('')
    print('#------------------------------------------------------------------#')
    print('#---------------------      New ISIS changes     ------------------#')
    print('#------------------------------------------------------------------#')
    print('')
    print('/configure router isis 5 overload-on-boot timeout 180')
    print('')

    for interface,description in interface_des.items():
        if 'B4A' in description:
            print('/configure router isis 5 {} level 1 metric 300'.format(interface))
        if 'B4B' in description:
            print('/configure router isis 5 {} level 1 metric 150'.format(interface))
            
##############################
    
    if ecmp_value[1] == '4':
        print('')
    else:
        print('#---------------------------------------------------------#')        
        print('######-----       Change ecmp metric        -------######')
        print('#---------------------------------------------------------#')
        print("# The router has ecmp value other than 4 , please change it to ecmp 4 for B4A")
        print('/configure router ecmp 4')
    print('#------------------------------------------------------------------#')
    print('#---------------------      New port changes     ------------------#')
    print('#------------------------------------------------------------------#')
    print('')
    for interface_desc, bfd in metric_interface_b4ab.items():
        if 'system' not in interface_desc:
            print('/configure router interface {} egress vlan-qos-policy "40013"'.format(interface_desc))
        if 'type' not in bfd and 'system' not in interface_desc:
            print('/configure router interface {} shutdown'.format(interface_desc))
            print('/configure router interface {} bfd 50 receive 50 multiplier 5 type fp'.format(interface_desc))
            print('/configure router interface {} no shutdown'.format(interface_desc))
        print('#------------------------------------------------------------------#')


# In[14]:


def bgp_remove_b4b():
    print('#---------------------------------------------------------#')        
    print('######-----       BGP Changes B4*             -------######')
    print('#---------------------------------------------------------#')
    #print('/configure router bgp no family')
    print('/configure router bgp no bfd-enable')
    print('/configure router bgp add-paths label-ipv4 send 2 receive')
    print('/configure router bgp selective-label-ipv4-install')
    print('/configure router bgp rapid-update vpn-ipv4 vpn-ipv6 evpn label-ipv4')
    print('/configure router bgp error-handling update-fault-tolerance')
    print('/config router bgp initial-send-delay-zero')
    print('#---------------------------------------------------------#')


def bgp_remove_b4c():
    print('#---------------------------------------------------------#')        
    print('######-----       BGP Changes  B4C          -------######')
    print('#---------------------------------------------------------#')
    print('/configure router bgp no keepalive')
    print('/configure router bgp no hold-time')
    print('/configure router bgp no bfd-enable')
    if '7705' not in router_type:
        print('/configure router bgp multi-path no ipv4')
        print('/configure router bgp multi-path no ipv6')
    if '7705' in router_type:
        print('/configure router bgp multipath 8')
    else:
        print('/configure router bgp multi-path maximum-paths 16')
        print('/configure router bgp rapid-update vpn-ipv4 vpn-ipv6 evpn label-ipv4')
        print('/configure router bgp add-paths label-ipv4 send 2 receive')
        print('/configure router bgp error-handling update-fault-tolerance')
    print('#---------------------------------------------------------#')


# In[15]:


def policy_bgp():
    print('#--------------------------------------------------------#')        
    print('######-----        ADD BGP Changes          -------######')
    print('#--------------------------------------------------------#')
    print('/configure router policy-options')
    print ('            begin')
    print ('            prefix-list "PRFX_DEFAULT"')
    print ('                prefix 0.0.0.0/0 exact')
    print ('                prefix ::/0 exact')
    print ('            exit')
    print ('            prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                prefix {}/32 exact'.format(system_ip))
    print ('            exit')
    print ('            commit')
    print ('        exit all')
    print('#--------------------------------------------------------#')        
    print('######-----      ADD Policy Changes         -------######')
    print('#--------------------------------------------------------#')
####################


def policy_remove():
    print('#--------------------------------------------------------#')
    print('## Cleaning LLD 1.2.1 prefix lists and communities ... ')
    print('#--------------------------------------------------------#')
    print('')
    print('/configure router policy-options')
    print('  begin')
    print('    no prefix-list "Default-Routes"')
    print('    no prefix-list "PRFX_LOCAL_SYSTEM_ADDRESS"')
    print('  commit')
    print('exit all')


# In[16]:


# Policies for B4A ##################################################
def policy_RR_5_ENSESR_AL_CSR():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_AL-CSR"')
    print('                description "EXPORT ROUTES TO CSRS"')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol evpn-ifl')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_AL-CSR"')
    print('                description "IMPORT ROUTES FROM CSRS"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "IMPORT BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "IMPORT EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')


def policy_RR_5_ENSESR_AL_BL():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_AL-BL"')
    print('                description "EXPORT ROUTES TO HUB BL"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol evpn-ifl')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "SEND BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_AL-BL"')
    print('                description "IMPORT ROUTES FROM HUB BL"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')

###############################################
def policy_RR_5_L3VPN_AL_CSR():
    print ('/configure router policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-L3VPN_AL-CSR"')
    print ('                description "EXPORT ROUTES TO CSRS"')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-vpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    description "PROPAGATE VPN ROUTES"')
    print ('                    from')
    print ('                        family vpn-ipv4 vpn-ipv6')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-L3VPN_AL-CSR"')
    print ('                description "IMPORT ROUTES FROM CSRS"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "IMPORT BGP LABELS"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "IMPORT VPN ROUTES"')
    print ('                    from')
    print ('                        family vpn-ipv4 vpn-ipv6')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit all')

################################################


# In[17]:


# Policies for B4B ##################################################

def policy_RR_5_ENSESR_BL_AL():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_BL-AL"')
    print('                description "EXPORT ROUTES TO HUB AL"')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "SEND BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "SEND EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_BL-AL"')
    print('                description "IMPORT ROUTES FROM HUB AL"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "IMPORT LEARNED BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "IMPORT LEARNED EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')    
    print ('            commit')
    print ('        exit all')

################################################################

def policy_RR_5_ENSESR_BL_BL():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_BL-BL"')
    print('                description "EXPORT ROUTES TO PEER HUB BL"')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "SEND LEARNED BGP LABEL"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "SEND LEARNED EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_BL-BL"')
    print('                description "IMPORT ROUTES FROM PEER HUB BL"')
    print('                entry 10')
    print('                    description "PREVENT LOOPBACK FROM REFLECTING BACK"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')

##############################################################

def policy_RR_5_ENSESR_BL_EBH():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_BL-EBH"')
    print('                description "EXPORT ROUTES TO EBH AL"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "SEND BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "SEND EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_BL-EBH"')
    print('                description "IMPORT ROUTES FROM EBH AL"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')



# In[18]:


# Policies for B4C ##################################################

def policy_RR_5_ENSESR_CSR_AL():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_CSR-AL"')
    print('                description "EXPORT ROUTES TO HUB ACCESS LEAF"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol evpn-ifl')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_CSR-AL"')
    print('                description "IMPORT ROUTES FROM HUB ACCESS LEAF"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')

############################

def policy_RR_5_ENSESR_SPOKE_CSR():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_SPOKE-CSR"')
    print('                description "EXPORT ROUTES TO A CSR"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                   exit')
    print('                    to')
    print('                        protocol evpn-ifl')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_SPOKE-CSR"')
    print('                description "IMPORT ROUTES FROM A CSR"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')

############################

def policy_RR_5_ENSESR_CSR_SPOKE():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-ENSESR_CSR-SPOKE"')
    print('                description "EXPORT ROUTES TO SPOKE CSRS"')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol evpn-ifl')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-ENSESR_CSR-SPOKE"')
    print('                description "IMPORT ROUTES FROM SPOKE CSRS"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    print('                    action drop')
    print('                    exit')
    print('                exit')
    print('                entry 10')
    print('                    description "IMPORT BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "IMPORT EVPN ROUTES"')
    print('                    from')
    print('                        evpn-type 5')
    print('                        family evpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                default-action drop')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')


########### This same policy if the node is a IXRE with L3VPN ###############
def policy_RR_5_L3VPN_CSR_SPOKE():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-L3VPN_CSR-SPOKE"')
    print('                description "EXPORT ROUTES TO A SPOKE"')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-vpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept     ')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    if router_type == '7250':
        #print('          if(routerType.Equals("7250IXR")){')
        print('                default-action drop')
        print('                exit')
    else:
        #print('          }else if(routerType.Equals("7705SAR")){')
        print('                default-action reject')
        print('            exit')
    print('            policy-statement "IMPORT_RR-5-L3VPN_CSR-SPOKE"')
    print('                description "IMPORT ROUTES FROM A SPOKE"')
    print('                entry 5')
    print('                    description "DEFAULT ROUTE PROTECTION"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    if router_type == '7250':
        #print('          if(routerType.Equals("7250IXR")){')
        print('                    action drop')
        print('                    exit')
    else:
        #print('          }else if(routerType.Equals("7705SAR")){')
        print('                    action reject')
        print('                exit')
    print('                entry 10')
    print('                    description "IMPORT BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "IMPORT VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    if router_type == '7250':
        #print('          if(routerType.Equals("7250IXR")){')
        print('                default-action drop')
        print('                exit')
    else:
        #print('          }else if(routerType.Equals("7705SAR")){')
        print('                default-action reject')
    print('            exit')
    print ('            commit')
    print ('        exit all')


def policy_RR_5_L3VPN_SPOKE_CSR():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-L3VPN_SPOKE-CSR"')
    print('                description "EXPORT ROUTES TO A CSR"')
    print('                entry 5')
    print('                    description "DEFAULT ROUTE PROTECTION"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    if router_type == '7250':
        #print('            if(routerType.Equals("7250IXR")){')
        print('                    action drop')
        print('                    exit')
    else:
        #print('            }else if(routerType.Equals("7705SAR")){')
        print('                    action reject')
        print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-vpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    if router_type == '7250':
        #print('          if(routerType.Equals("7250IXR")){')
        print('                default-action drop')
    else:
        #print('          }else if(routerType.Equals("7705SAR")){')
        print('                default-action reject')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-L3VPN_SPOKE-CSR"')
    print('                description "IMPORT ROUTES FROM A CSR"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')

#################################

def policy_RR_5_L3VPN_CSR_AL():
    print('/configure router policy-options')
    print ('            begin')
    print('            policy-statement "EXPORT_RR-5-L3VPN_CSR-AL"')
    print('                description "EXPORT ROUTES TO HUB ACCESS LEAF"')
    print('                entry 5')
    print('                    description "DROP DEFAULT ROUTE"')
    print('                    from')
    print('                        prefix-list "PRFX_DEFAULT"')
    print('                    exit')
    if router_type == '7250':
        #print('            if(routerType.Equals("7250IXR")){')
        print('                    action drop')
        print('                    exit')
    else:
        #print('            }else if(routerType.Equals("7705SAR")){')
        print('                    action reject')
        print('                exit')
    print('                entry 10')
    print('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print('                    from')
    print('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 20')
    print('                    description "PROPAGATE CONNECTED ROUTES"')
    print('                    from')
    print('                        protocol direct')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-vpn')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    print('                exit')
    print('                entry 30')
    print('                    description "PROPAGATE BGP LABELS"')
    print('                    from')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    to')
    print('                        protocol bgp-label')
    print('                    exit')
    print('                    action accept')
    print('                        aigp-metric igp')
    print('                    exit')
    print('                exit')
    print('                entry 40')
    print('                    description "PROPAGATE VPN ROUTES"')
    print('                    from')
    print('                        family vpn-ipv4 vpn-ipv6')
    print('                    exit')
    print('                    action accept')
    print('                    exit')
    if router_type == '7250':
        #print('          if(routerType.Equals("7250IXR")){')
        print('                default-action drop')
        print('                exit')
    else:
        #print('          }else if(routerType.Equals("7705SAR")){')
        print('            exit')
        print('                default-action reject')
    print('            exit')
    print('            policy-statement "IMPORT_RR-5-L3VPN_CSR-AL"')
    print('                description "IMPORT ROUTES FROM HUB ACCESS LEAF"')
    print('                default-action accept')
    print('                exit')
    print('            exit')
    print ('            commit')
    print ('        exit all')


# In[19]:


def extract_bgp_neighbors(data, start_key, end_key, find_value):
    global return_value, cluster
    return_value = {}
    cluster = None

    try:
        # Find the start of the group block (start_key)
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        
        # Find the next occurrence of 'group' after the current start_key
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))

        #print(f"Processing group from {group_start_idx} to {group_end_idx}")

        in_neighbor_block = False
        current_neighbor_ip = None
        
        # Process only the current group block
        for i in range(group_start_idx, group_end_idx):
            line = data.at[i, 'config'].strip()

            # Capture the cluster value if it exists
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
                #print(f"Cluster: {cluster}")

            # Start tracking neighbor IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
                #print(f"Neighbor IP: {current_neighbor_ip}")

            # Capture description if within a neighbor block
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:  # Ensure 'find_value' is in description
                    return_value[current_neighbor_ip] = description
                    #print(f"Description: {description}")

            # Reset block flag on exit
            elif line == 'exit':
                in_neighbor_block = False

    except IndexError:
        print("# The target BGP group was not found in the file.")
    
    return return_value, cluster



# In[20]:


def new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy):
    print('#--------------------------------------------------------#')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#--------------------------------------------------------#')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print('        exit all')
    print('')
    print('#--------------------------------------------------------#')        
    print('######-----        Add New BGP Group        -------######')
    print('#--------------------------------------------------------#')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    # Only print the cluster value if it exists (not None)
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print ('                import "{}"'.format(new_import_policy))
    print ('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                advertise-inactive')
    print('                bfd-enable')
    print('                aigp')

    # Loop through neighbors and descriptions in return_value
    for csr_neighbor_ip, description in return_value.items():
        print('                neighbor {}'.format(csr_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')

    print('exit all')
    print('#--------------------------------------------------------#')
#############################################################################################

def new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy):
    
    print('#--------------------------------------------------------#')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#--------------------------------------------------------#')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print('        exit all')
    print('')
    print('#--------------------------------------------------------#')        
    print('######-----        Add New BGP Group        -------######')
    print('#--------------------------------------------------------#')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family vpn-ipv4 vpn-ipv6 label-ipv4')
    if 'B4A' in name:
        print('                type internal')

    # Only print the cluster value if it exists (not None)
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print ('                import "{}"'.format(new_import_policy))
    print ('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    if '7705' in router_type:
        local_as = my_file_pd['config'][ my_file_pd.index[my_file_pd['config'].str.contains('local-as')].tolist()[0]].split()[1]
        print ('                local-as {}'.format(local_as))
        print ('                peer-as {}'.format(local_as))
    #print('                advertise-inactive')
    print('                bfd-enable')
    print('                aigp')

    # Loop through neighbors and descriptions in return_value
    for csr_neighbor_ip, description in return_value.items():
        print('                neighbor {}'.format(csr_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')

    print('exit all')
    print('#--------------------------------------------------------#')


# In[21]:


######################## Groups for B4A ###########################

def rr_5_ensesr_bl_b4a(): # Facing B4B (Hub BL-01 and 02)
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	if 'B4A' in name:
		find_value = 'B4B'
	else:
		find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_BL"' 
	new_description = 'Neighbor group for Hub BL' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_AL-BL'

    # Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


def rr_5_ensesr_csr_b4a(): # B4A Facing IXRE DRAN downstream
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"' 
	new_description = 'Neighbor group for EVPN DRAN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_AL-CSR' 

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)




# In[22]:


######################## Groups for B4B ###########################

def rr_5_client_b4b(): #  B4B Facing b40
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"' #
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT' #
	end_key = 'echo "Log all events for service vprn' 
	find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_EBH"' 
	new_description = 'Neighbor group for EBH AL' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_BL-EBH'
	
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_peer_b4b():  #  Facing B4B
	data = my_file_pd
	start_key =  'group "RR-5-PEER"'
	old_import_policy = 'IMPORT_RR-5-PEER' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4B'
	new_group = 'group "RR-5-ENSESR_PEER"' 
	new_description = 'Neighbor group for PEER HUB BL' #
	new_import_policy = 'IMPORT_RR-5-ENSESR_BL-BL' #
	
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_ENSESR_b4b():  #  Facing B4A
	data = my_file_pd
	start_key =  'group "RR-5-ENSESR"'
	old_import_policy = 'IMPORT_RR-5-ENSESR' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4A'
	new_group = 'group "RR-5-ENSESR_AL"' 
	new_description = 'Neighbor group for HUB AL' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_BL-AL'
    # Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


# In[23]:


######################## Groups for B4C  #####################

def rr_5_ENSESR_b4c(): #  7250 Hub facing B4A
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"'
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4A'
	new_group = 'group "RR-5-ENSESR_AL"' #
	new_description = 'Neighbor group for HUB AL' #
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-AL' #
    
# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_ENSESR_spoke_b4c(): #  Spoke Facing hub IXRE B4C
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR-CLIENT"' #
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' #
	new_import_policy = 'IMPORT_RR-5-ENSESR_SPOKE-CSR' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_ENSESR_b4c_spoke(): #   Hub Facing spoke IXRE B4C
	data = my_file_pd
	start_key = 'group "RR-5-ENSESR"' #
	old_import_policy = 'IMPORT_RR-5-ENSESR' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN SPOKE' #
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-SPOKE' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_l3vpn_b4c_hub(): #   7250 Hub Facing B4A with l3vpn
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN-CLIENT"' #
	old_import_policy = 'IMPORT_RR-5-L3VPN-CLIENT' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4A'
	new_group = 'group "RR-5-L3VPN_AL"'
	new_description = 'Neighbor group for EVPN SPOKE' #
	new_import_policy = 'IMPORT_RR-5-L3VPN_CSR-AL' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)

def rr_5_ENSESR_7705_b4c(): #   B4A having a 7705 connected
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN"' #
	old_import_policy = 'IMPORT_RR-5-L3VPN' #
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-L3VPN_CSR"'
	new_description = 'Neighbor group for L3VPN CSR'
	new_import_policy = 'IMPORT_RR-5-L3VPN_AL-CSR'

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


def rr_5_7705h_7705_spoke(): # 7705 Hub facing 7705 Spoke
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-L3VPN'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-L3VPN_SPOKE"' #
	new_description = 'Neighbor group for L3VPN SPOKE' #
	new_import_policy = 'IMPORT_RR-5-L3VPN_CSR-SPOKE' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)
    
######################################################################

def rr_5_7705_csr_b4a(): # 7705 SA facing B4A 
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-L3VPN-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4A'
	new_group = 'group "RR-5-L3VPN_AL"' #
	new_description = 'Neighbor group for L3VPN HUB Access Leaf' #
	new_import_policy = 'IMPORT_RR-5-L3VPN_CSR-AL' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)
######################################################################


def rr_5_7705s_7705h(): # 7705 Spoke facing 7705 Hub 
	data = my_file_pd
	start_key = 'group "RR-5-L3VPN-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-L3VPN-CLIENT'
	end_key = 'echo "Log all events for service vprn'
	find_value = 'B4C'
	new_group = 'group "RR-5-L3VPN_CSR"' #
	new_description = 'Neighbor group for L3VPN CSR' #
	new_import_policy = 'IMPORT_RR-5-L3VPN_SPOKE-CSR' #

# Extract neighbors and cluster
	neighbors, cluster_value = extract_bgp_neighbors(data, start_key, end_key, find_value)
	new_7705_bgp_group(new_group, new_description,cluster_value, return_value, start_key, old_import_policy, new_import_policy)


# In[24]:


# B40 group change and check interface to 1000000

def b40_01_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ONLY after adding the bgp on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------------#')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------------#')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    #print ('/configure router isis 5 interface " level 1 metric 1000000
    print ('# If the above interface level 1 metric is not 1000000 then change it to 1000000')


def b40_02_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group after you have brought up 135 BGP neigh on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------------#')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------------#')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    print ('# If the interface level 1 metric is not 1000000 then change it to 1000000')


# B40 group change and check interface to 1000000

def b40_01_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-01     "')
    print ('#--------------------------------------------------------#')
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_BL" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------------#')


def b40_02_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-02     "')
    print ('#--------------------------------------------------------#')
    print ('/configure router bgp group "RR-5-ENSESR_BL" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_BL" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------------#')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------------#')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    print ('# If the interface level 1 metric is not 1000000 then change it to 1000000')


# In[25]:


# Post check ping check script / 
def pre_post_b40():
    print ('')
    print ('#--------------------------------------------------------#')
    print ('# Local IXRE post checks "')
    print ('#--------------------------------------------------------#')
    print ('show service sap-using')
    print ('show port A/gnss')
    print ('show system ptp port')
    print ('show router 1 interface')
    print ('show router 4 interface')
    print ('show router policy')
    print ('show router bgp summary')
    print ('')

def post_b40_ping():
    print ('#--------------------------------------------------------#')
    print ('# B40 post checks for pinging CSR interfaces from B40-01 and 02"')
    print ('#--------------------------------------------------------#')
    print('\show router bgp summary')
    for ran in vprn1_ip:
        print('ping router-instance "RAN" {}'.format(ran.split('/', 1)[0][8:]))
    for mgm in vprn4_ip:
        print('ping router-instance "CELL_MGMT" {}'.format(mgm.split('/', 1)[0][8:]))


# In[26]:


def b4a_qos():
    print ('#--------------------------------------------------------#')
    print ('#------------            Add OQS B4A          -----------"')
    print ('#--------------------------------------------------------#')
    print('/configure qos')
    print('        vlan-qos-policy "40011"')
    print('            queue "8" create')
    print('                no queue-type')
    print('                exit')
    print('        exit')
    print('        egress-remark-policy "40021"')
    print('            fc ef create')
    print('                lsp-exp in-profile 5 out-profile 5')
    print('            exit')
    print('        exit')
    print('        sap-ingress 41032 name "41032" create')
    print('            ingress-classification-policy "41032"')
    print('        exit')
    print('exit all')


# In[27]:


def b4b_b40_bgp_conf():
    for interface_desc, description in metric_b40.items():
        #print(description)
        if 'B40-01' in description:
            # B40-01 changes in a new file #################################
            sys.stdout = open(folder + '/' + name +'_B40-01.txt','w')
            b40_01_changes_ixre(system_ip, name)
            b40_01_rollback_ixre(system_ip, name)
    
        if 'B40-02' in description:
            # B40-02 changes in a new file #################################
            sys.stdout = open(folder + '/' + name +'_B40-02.txt','w')
            b40_02_changes_ixre(system_ip, name)
            b40_02_rollback_ixre(system_ip, name)    

def pre_checks():
    print('########### Following info is Just to verify the interface and all system info ############')
    print('# System Name: {}", "system ip: {}" , " Router Type: {}"'.format(name, system_ip, router_type))
    print('##############################################################')
    print('')
    print('###-----      create system rollback     -------###')
    print('')
    print('/show system rollback')
    print('/admin rollback save comment "Pre-update Checkpoint"')
    print('')
    print('###-----     Precheck commands to run before start of work -----###')
    print('')
    print('\show version ')
    print('\show bof ')
    print('\show chassis ')
    print('\show system memory-pools ')
    print('\show card ')
    print('\show mda ')
    print('\show port ')

def system_conf_7705():
    if '7705' in router_type:
        print('')
        print('#--------------------------------------------------------#')
        print('echo "System Security Configuration"')
        print('#--------------------------------------------------------#')
        print('/configure')
        print('    system ')
        print('        security')
        print('            no ftp-server')
        print('            no telnet-server')
        print('            no telnet6-server')
        print('        exit')
        print('exit all')
        print('#--------------------------------------------------------#')
        print('echo "Log Configuration"')
        print('#--------------------------------------------------------#')
        print('/configure')
        print('    log')
        print('       filter 10')
        print('           default-action drop')
        print('           entry 10')
        print('                action forward')
        print('                match')
        print('                     application eq "chassis"')
        print('                     number eq 2059')
        print('                     message eq pattern "detected egress FCS errors on complex"')
        print('                exit')
        print('            exit')
        print('        exit')
        print('exit all')


# In[28]:


def main():
    global items
    global folder
    all_files()
    for items in path:
        create_pd()
        if not os.path.isdir(name):
            os.mkdir(name)
            os.chdir(name)
            folder = os.getcwd()
        else:
            os.chdir(name)
            folder = os.getcwd()

        if 'B4A' in name:
            # Check for the B4A
            policy_bl_b4a= my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR-CLIENT"')].tolist() # east or west ring router but not B40
            policy_csr_b4a = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR"')].tolist() #--- These are spokes and CSR 
            policy_b4a_7705 = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-L3VPN"')].tolist() # B4A facing the 7705 
            # Bool check B4A
            b4b_bl_b4a_exists = bool(policy_bl_b4a)
            b4c_csr_b4a_exists = bool(policy_csr_b4a)
            b4a_7705_exists = bool(policy_b4a_7705)
            
            sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
            pre_checks()
            b4a_qos()
            metric_interface_b4a()
            port_bfd(my_file_pd)
            policy_bgp()

            if b4b_bl_b4a_exists:
                policy_RR_5_ENSESR_AL_BL()
                rr_5_ensesr_bl_b4a() # group "RR-5-ENSESR-CLIENT"
                
            if b4c_csr_b4a_exists:
                policy_RR_5_ENSESR_AL_CSR()
                rr_5_ensesr_csr_b4a()     # group "RR-5-ENSESR"
                
            if b4a_7705_exists:
                policy_RR_5_L3VPN_AL_CSR()
                rr_5_ENSESR_7705_b4c()    # group "RR-5-L3VPN"

            bgp_remove_b4b()
            policy_remove()
            # BOF config changes
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            get_bof(my_file_pd)
            bof_data()
            create_bof(old_statics)

            # Post checks file generation
            sys.stdout = open(folder + '/' + name +'_Post_Checks.txt','w')
            pre_post_b40()
        ##############################################################################

        if 'B4B' in name:
            # Check for the B4B
            policy_HUB_BL = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR-CLIENT"')].tolist() # east or west ring router but not B40
            policy_BL_BL = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-PEER"')].tolist() #--- These are spokes and CSR 
            policy_BL_AL = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR"')].tolist()
            
            # Bool check
            b4b_hub_bl_exists = bool(policy_HUB_BL)
            b4c_bl_bl_exists = bool(policy_BL_BL)
            b4c_bl_al_exists = bool(policy_BL_AL)
            
            sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
            pre_checks()
            ip_filter_10005_b4b()
            print_metric_interface_b4b()
            port_bfd(my_file_pd)
            bgp_remove_b4b()
            policy_bgp()
            if b4b_hub_bl_exists:
                policy_RR_5_ENSESR_BL_EBH()
                rr_5_client_b4b() # "RR-5-ENSESR-CLIENT" to "RR-5-ENSESR_EBH" HUB AL
            if b4c_bl_bl_exists:
                policy_RR_5_ENSESR_BL_BL()
                rr_5_peer_b4b() # 'group "RR-5-PEER" to "RR-5-ENSESR_PEER" BL-BL
            if b4c_bl_al_exists:
                policy_RR_5_ENSESR_BL_AL()
                rr_5_ENSESR_b4b() # 'group "RR-5-ENSESR" to "RR-5-ENSESR_AL" BL-AL
            policy_remove()
            
            # BOF config changes #################################
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            get_bof(my_file_pd)
            bof_data()
            create_bof(old_statics)
                        
            # Run the following B40 script based on the B40-01 or 02 the node is connected to.
            b4b_b40_bgp_conf()      
            
            # Post checks file generation #################################
            sys.stdout = open(folder + '/' + name +'_Post_Checks.txt','w')
            pre_post_b40()
        ##############################################################################

        if 'B4C' in name:
            # Check for the B4C, B4S, B4E
            policy_CSR_B4C = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR-CLIENT"')].tolist() # east or west ring router but not B40
            policy_CSR_7705 = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-L3VPN-CLIENT"')].tolist() #--- These are spokes and CSR 
            policy_7705h_7705s = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-L3VPN"')].tolist() # 77-5 HUB facing the 7705 
            policy_CSR_B4C_spoke = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR"')].tolist() # 77-5 HUB facing the 7705 
            
            # Bool check B4C, B4S, B4E
            b4c_ixre_sa_exists = bool(policy_CSR_B4C)
            b4c_7705_sa_exists = bool(policy_CSR_7705)
            b4c_7705h_7705s_exists = bool(policy_7705h_7705s)
            b4c_ixre_spoke_exists = bool(policy_CSR_B4C_spoke)
            
            sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
            pre_checks()
            system_conf_7705()
            metric_int_b4c(my_file_pd)
            interface_b4c()
            port_bfd(my_file_pd)
            bgp_remove_b4c()
            policy_bgp()
            if b4c_ixre_sa_exists: #( Both SA and HUB 7250 evpn)
                if int_b4_value == 'B4A' or port_b4a_value == 'B4A': # if B4A in the interface desc
                    policy_RR_5_ENSESR_CSR_AL()
                    rr_5_ENSESR_b4c() # "RR-5-ENSESR-CLIENT" has a spoke
                elif int_b4_value == None: #or int_b4_value is None: # if no B4A in the interface desc
                    policy_RR_5_ENSESR_SPOKE_CSR()
                    rr_5_ENSESR_spoke_b4c()

            if b4c_ixre_spoke_exists:    # HUB having spoke
                policy_RR_5_ENSESR_CSR_SPOKE()
                rr_5_ENSESR_b4c_spoke()

            if b4c_7705_sa_exists:
                if '7705' in router_type:
                    if int_b4_value == 'B4A' or port_b4c_value == 'B4A': # if B4A in the interface desc
                        policy_RR_5_L3VPN_CSR_AL()
                        rr_5_7705_csr_b4a() # 'group "RR-5-L3VPN-CLIENT" to "RR-5-L3VPN_AL" SA 7705
                    else:
                        policy_RR_5_L3VPN_SPOKE_CSR()
                        rr_5_7705s_7705h() # 'group "RR-5-L3VPN-CLIENT" to HUB 7705  ##
                    
                if '7250' in router_type:
                    policy_RR_5_L3VPN_CSR_AL()
                    rr_5_l3vpn_b4c_hub()
            
            if b4c_7705h_7705s_exists:
                policy_RR_5_L3VPN_CSR_SPOKE()
                rr_5_7705h_7705_spoke()
            policy_remove()
            # BOF config changes #################################
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            get_bof(my_file_pd)
            bof_data()
            create_bof(old_statics)
       
            # Post checks file generation #################################
            sys.stdout = open(folder + '/' + name +'_Post_Checks.txt','w')
            pre_post_b40()

        ##################################

        if 'B4S' in name:
            sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
            metric_int_b4c(my_file_pd)
            interface_qos_b4s()
            
            # BOF config changes #################################
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            get_bof(my_file_pd)
            bof_data()
            create_bof(old_statics)
        ##################################

        if 'B4E' in name:
            sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
            port_b4e(my_file_pd)
                        
            # BOF config changes #################################
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            get_bof(my_file_pd)
            bof_data()
            create_bof_b4e(old_statics)
            
        os.chdir("..")  # Move up one directory


# In[29]:


if __name__ == "__main__":
    if check_for_update():
        restart_script()
    else:
        main()


# In[ ]:




