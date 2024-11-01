#!/usr/bin/env python
# coding: utf-8

# In[1]:


# Import required libraries
import pandas as pd
import os
import sys
import re
import logging
from datetime import datetime
from itertools import islice


# In[2]:


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


# In[3]:


# Create a list of path for all the scanned files above.
def all_files():
    scan_file()
    global path
    path = []
    for i in range(len(my_files)):
        path.append(cwd+"/"+my_files[i])
    return path


# In[4]:


# Read the contents and extract the file name
def create_pd():
    global name, my_file_pd, router_type, ecmp_value, system_ip

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
        print("# No ecmp found")
    
    sys = my_file_pd.index[my_file_pd['config'].str.contains('router-id')]
    router_id_row = my_file_pd['config'][sys].iloc[0]
    match = re.search(r'router-id\s+(\d+\.\d+\.\d+\.\d+)', router_id_row)
    if match:
        system_ip = match.group(1)
        #print(f"Extracted IP address: {system_ip}")
    else:
        print("No IP address found.")
        


# In[5]:


def b40_name_get():
    global b40_name
    
    import_string = 'import "IMPORT_RR-5-ENSESR-CLIENT"'
    import_index = my_file_pd.index[my_file_pd['config'] == import_string].tolist()
    
    # Step 2: If the import string is found, iterate the next 10 rows to look for 'description' containing 'B40'
    b40_name = []
    description_pattern = re.compile(r'description.*B40', re.IGNORECASE)
    
    if import_index:
        for idx in import_index:
            # Check the next 10 lines after the 'import' line
            for i in range(idx + 1, min(idx + 8, len(my_file_pd))):
                if description_pattern.search(my_file_pd.loc[i, 'config']):
                    b40_name.append({
                        #'import': my_file_pd.loc[idx, 'config'],
                        'description': my_file_pd.loc[i, 'config']
                    })
                    break
    b40_name = my_file_pd.loc[i, 'config']
    b40_name = b40_name[-15:-1]
    return b40_name


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
    return old_statics

def create_bof(old_statics):
    get_bof(my_file_pd)
    bof_data()
    print('')
    print('#--------------------------------------------------')
    print('#System Name: {}"'.format(name))
    print('#--------------------------------------------------')
    print('########### Adding the New Static Routes ############')
    print('')
    print(static_route_new_1)
    print(static_route_new_2)
    print(static_route_new_3)
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


# In[7]:


def extract_vprn_info(data):
    global vprn_value
    vprn_value = {}
    current_vprn = None  # To hold the current VPRN block (either 1 or 4)

    
    # Find the start index for the block
    group_start_idx = data[data['config'].str.contains('echo "Service')].index[0]
    # Slice the DataFrame starting from group_start_idx and search for the next 'echo ' string
    echo_slice = data.loc[group_start_idx:]
    group_end_idx = echo_slice[echo_slice['config'].str.contains('echo "Router')].index[0]
    #print(group_start_idx, group_end_idx)
    
    in_vprn_block = False
    current_interface = None
    for i in range(group_start_idx, group_end_idx):
        line = data.at[i, 'config'].strip()

        # Print the current line for debugging
        #print(f"Processing line {i}: {line}")
        # Start tracking VPRN block if it is 'vprn 1' or 'vprn 4'
        if line.startswith('vprn 1') or line.startswith('vprn 4'):
            current_vprn = line.split()[1]
            in_vprn_block = True
            #print(f"Entering VPRN block: {current_vprn}")
        # Capture interface name within a VPRN block
        elif line.startswith('interface') and in_vprn_block:
            current_interface = line.split('"')[1]  # Extract the interface name
            vprn_value[current_vprn] = vprn_value.get(current_vprn, {})
            vprn_value[current_vprn][current_interface] = {}
            #print(f"Captured interface: {current_interface} under VPRN {current_vprn}")
        # Capture the IPv6 address within a VPRN block and interface
        elif line.startswith('address') and in_vprn_block and current_interface:
            address = line.split()[1]  # Extract the address
            vprn_value[current_vprn][current_interface]['address'] = address
            #print(f"Captured address: {address} for interface {current_interface} under VPRN {current_vprn}")
        # Reset block flag when the 'exit' statement is found
        elif line == 'exit' and in_vprn_block:
            #print(f"Exiting VPRN block: {current_vprn}")
            current_interface = None
              # Close the VPRN block
    ##################################################################################################
    #return vprn_value



# In[8]:


# Get the interfaces for which the metric has to be changed.
def metric_int(data):
    global metric_interface
    metric_interface = {}
    try:
        # Find the start of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.fullmatch('router Base')].index[0] #Find the index of the line containing 'group "RR-5-ENSESR"'.
        
        # Loop through the subsequent lines to find neighbors and descriptions
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        interface_desc = None
    
        for i in range(group_start_idx + 1, len(data)):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('interface'):
                in_neighbor_block = True
                interface_desc = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' in description:  # Check if description does not contain "B40"
                    metric_interface[interface_desc] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("No B40 interface was found")
    #for interface_desc, description in metric_interface.items():
     #   print('/configure router isis 5 {} level 1 metric 1000000'.format(interface_desc))
    return metric_interface


# In[9]:


# This is only for the node which is connected to B40, it will check for CSR connected to it and the spokes in the ring.
# So only looking for group "RR-5-ENSESR.

def extract_neighbors(data, start_key, find_value):
    global spoke_bgp_neighbors
    global csr_bgp_neighbors
    spoke_bgp_neighbors = {}
    csr_bgp_neighbors = {}
    cluster = None
    
    try:
        # Find the start and end of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False
        current_neighbor_ip = None
        
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' not in description and 'Spoke' in description: # Check if there is no B40 but spoke in description
                    spoke_bgp_neighbors[current_neighbor_ip] = description
                elif 'B40' not in description and 'Spoke' not in description: # Check if there is no B40 and no spoke in description
                    csr_bgp_neighbors[current_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("# The target group was not found in the file.")
    
    return spoke_bgp_neighbors, csr_bgp_neighbors, cluster

def add_spoke_csr_bgp_neighbors(new_group, new_description, spoke_csr_bgp_neighbors, cluster, return_value, start_key, old_import_policy, new_import_policy):
    print('#---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    for spoke_neighbor_ip, description in spoke_csr_bgp_neighbors.items():
        print('                neighbor {}'.format(spoke_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')
    print('exit all')
    print('#--------------------------------------------------')     


# Print all the spoke nodes under Old group "RR-5-ENSESR"
def rr_5_ensesr_spoke():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN SPOKE' 
	new_import_policy = 'IMPORT_RR-5-ENSESR-SPOKE' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)

# Not tested"
def rr_5_csr_spoke():
    start_key = 'group ' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR-CSR' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, csr_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)

# Print all the spoke nodes under Old group "RR-5-ENSESR" to new group "RR-5-ENSESR_SPOKE"
def rr_5_ensesr_spoke_IRR():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN SPOKE' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-SPOKE' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)


# Print all the spoke nodes under Old group "RR-5-ENSESR"
def RR_5_ENSESR_IRRW_SPOKE():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN SPOKE' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-SPOKE' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)


def RR_5_ENSESR_IRRW_CSR():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-CSR' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, csr_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)


#East Spokes

# Print all the spoke nodes under Old group "RR-5-ENSESR"
def RR_5_ENSESR_IRRE_SPOKE(spoke_bgp_neighbors):
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN SPOKE' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-SPOKE' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)


def RR_5_ENSESR_IRRE_CSR():
    start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
	find_value = 'B4C'
	new_group = 'group "RR-5-ENSESR_CSR"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-CSR' 
    # Extract neighbors and cluster
    spoke_bgp_neighbors, csr_bgp_neighbors, cluster = extract_neighbors(my_file_pd, start_key)
    add_spoke_csr_bgp_neighbors(new_group, new_description, csr_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy)



# In[10]:


def extract_spoke_neighbors(data, start_key, find_value):
    global csr_spoke_bgp_neighbors
    csr_spoke_bgp_neighbors = {}
    cluster = None
    try:
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False
        current_neighbor_ip = None
        
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                current_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if 'B40' not in description and 'Spoke' not in description:  # Ensure no B40 or Spoke in the description
                    csr_spoke_bgp_neighbors[current_neighbor_ip] = description
                # End neighbor block on encountering "exit"
                in_neighbor_block = False
    except IndexError:
        print('# The target group {} was not found in the file.'.format(start_key))
    
    return csr_spoke_bgp_neighbors, cluster

def new_spoke_bgp_group(new_group, new_description, csr_spoke_bgp_neighbors, return_value, start_key, old_import_policy, new_import_policy): # This group and policies are for the spoke only
    print('#---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    if cluster_value is not None:
        print('                cluster {}'.format(cluster_value))
    print('                import "{}"'.format(new_import_policy))
    print('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print('                bfd-enable')
    print('                aigp')
    for csr_neighbor_ip, description in csr_spoke_bgp_neighbors.items():
        print('                neighbor {}'.format(csr_neighbor_ip))
        print('                    description "{}"'.format(description))
        print('                    authentication-key "eNSEbgp"')
        print('                exit')
    print('exit all')
    print('#--------------------------------------------------')
    
def rr_5_csr_end_spoke(csr_spoke_bgp_neighbors): # This group and policies are for the spoke only
	start_key = 'group "RR-5-ENSESR"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-ENSESR'
	find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_SPOKE"'
	new_description = 'Neighbor group for EVPN CSR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-SPOKE' 
    # Extract neighbors and cluster
	csr_spoke_bgp_neighbors, cluster = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_spoke_bgp_group(new_group, new_description, csr_spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy )


def rr_5_csr_end_spoke_IRR(csr_spoke_bgp_neighbors): # This group and policies are for the spoke only 
	start_key = 'group " RR-5-ENSESR-CLIENT"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-PEER'
	find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_IRR"'
	new_description = 'Neighbor group for EVPN IRR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_CSR-IRR' 
    # Extract neighbors and cluster
	csr_spoke_bgp_neighbors = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_spoke_bgp_group(new_group, new_description, csr_spoke_bgp_neighbors, cluster, start_key, old_import_policy, new_import_policy )



# In[11]:


# --- This is non B40 ring router
def extract_ring_neighbors(data, start_key, find_value):
    global ring_neighbors
    # Initialize a dictionary to store neighbors and their descriptions
    ring_neighbors = {}
    cluster = None
    try:
        group_start_idx = data[data['config'].str.contains(start_key)].index[0]
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))

        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        ring_neighbor_ip = None
    
        for i in range(group_start_idx + 1, group_end_idx):
            line = data.at[i, 'config'].strip()
            if line.startswith('cluster'):
                cluster = line.split()[1]  # Store the cluster IP
            if line.startswith('neighbor'):
                in_neighbor_block = True
                ring_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value not in description:  # Check if description does not contain "B40"
                    ring_neighbors[ring_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("The target group 'RR-5-PEER' was not found in the file.")
    
    return ring_neighbors, cluster
 


def new_ring_bgp_group(new_group, new_description, neighbors, cluster, return_value, start_key, old_import_policy, new_import_policy):
    print('#---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('#---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit all')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print('                family evpn label-ipv4')
    print('                type internal')
    # Only print the cluster value if it exists (not None)
    if ring_neighbors:
    # Extract the first (and only) key and value
        ring_neighbor_ip = next(iter(ring_neighbors.keys()))
        description = ring_neighbors[ring_neighbor_ip]
        print ('                neighbor {}'.format(ring_neighbor_ip))
        print ('                    description "{}"'.format(ring_neighbors[ring_neighbor_ip]))
        print ('                    authentication-key "eNSEbgp"')
        print ('                exit')
    print('exit all')
    print('#--------------------------------------------------')


def rr_5_ensesr_csr_peer():
	start_key = 'group "RR-5-PEER"' #(Old group name)
	old_import_policy = 'IMPORT_RR-5-PEER'
	find_value = 'B40'
	new_group = 'group "RR-5-ENSESR_IRR"'
	new_description = 'Neighbor group for EVPN IRR' 
	new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-IRR' 
    # Extract neighbors and cluster
	neighbors, cluster = extract_ring_neighbors(my_file_pd, start_key, find_value)
	new_ring_bgp_group(new_group, new_description,neighbors,cluster, start_key, old_import_policy, new_import_policy)



# In[14]:


#--- This is non B40 ring router
def extract_b40_neighbors(data, start_key, find_value):
    global b40_neighbors
    b40_neighbors = {}
    try:
        # Find the start of the group "RR-5-ENSESR"
        group_start_idx = data[data['config'].str.contains(start_key)].index[0] #Find the index of the line containing 'group "RR-5-ENSESR"'.
        group_end_idx_candidates = data[data['config'].str.contains(r'group ')].index.tolist()
        group_end_idx = next((idx for idx in group_end_idx_candidates if idx > group_start_idx), len(data))
        
        in_neighbor_block = False #Use a flag in_neighbor_block to track if we are within a neighbor block.
        b40_neighbor_ip = None
    
        for i in range(group_start_idx + 1, len(data)):
            line = data.at[i, 'config'].strip()
            
            if line.startswith('neighbor'):
                in_neighbor_block = True
                b40_neighbor_ip = line.split()[1]
            elif line.startswith('description') and in_neighbor_block:
                description = line.split(' ', 1)[1].strip('"')
                if find_value in description:  # Check if description does not contain "B40"
                    b40_neighbors[b40_neighbor_ip] = description
                in_neighbor_block = False
            elif line == 'exit':
                in_neighbor_block = False
    except IndexError:
        print("The target group 'RR-5-PEER' was not found in the file.")
    
    return b40_neighbors


def add_b40_neighbors(new_description, new_import_policy, old_import_policy):
    print('##---------------------------------------------------------')        
    print('######-----       Delete Old BGP Group      -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {} shutdown'.format(start_key))
    print('    no {}'.format(start_key))
    print('        exit')
    print('/configure router policy-options')
    print ('            begin')
    print('    no policy-statement "{}"'.format(old_import_policy))
    print('    no policy-statement "{}"'.format(old_import_policy.replace("IMPORT", "EXPORT")))
    print('        exit all')
    print ('            commit')
    print ('        exit')
    print ('exit all')
    print('')
    print('##---------------------------------------------------------')        
    print('######-----        Add New BGP Group        -------######')
    print('##---------------------------------------------------------')
    print('/configure router bgp')
    print('    {}'.format(new_group))
    print('                description "{}"'.format(new_description))
    print ('                family evpn label-ipv4')
    print ('                type internal')
    print ('                import "{}"'.format(new_import_policy))
    print ('                export "{}"'.format(new_import_policy.replace("IMPORT", "EXPORT")))
    print ('                bfd-enable')
    print ('                aigp')
    if b40_neighbors:
    # Extract the first (and only) key and value
        b40_neighbor_ip = next(iter(b40_neighbors.keys()))
        description = b40_neighbors[b40_neighbor_ip]
        print ('                neighbor {}'.format(b40_neighbor_ip))
        print ('                    description "{}"'.format(b40_neighbors[b40_neighbor_ip]))
        print ('                    authentication-key "eNSEbgp"')
        print ('                exit')
    print ('exit all')
    print ('#--------------------------------------------------')



def rr_5_ensesr_ebh():
    start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B40'
    new_group = 'group "RR-5-ENSESR_EBH"'
    new_description = 'Neighbor group for EVPN EBH Acess Leaf' 
    new_import_policy = 'IMPORT_RR-5-ENSESR-EBH'
    b40_neighbors = extract_ring_neighbors(my_file_pd, start_key, find_value)
    add_b40_neighbors(new_description, b40_neighbors, new_import_policy, old_import_policy)

def rr_5_ensesr_irrw_ebh():
    start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B40'
    new_group = 'group "RR-5-ENSESR_EBH"'
    new_description = 'Neighbor group for EVPN EBH Acess Leaf' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRE-EBH'
    b40_neighbors = extract_ring_neighbors(my_file_pd, start_key, find_value)
    add_b40_neighbors(new_description, b40_neighbors, new_import_policy, old_import_policy)

def rr_5_ensesr_irre_ebh():
    start_key = 'group "RR-5-ENSESR-CLIENT"' #(Old group name)
    old_import_policy = 'IMPORT_RR-5-ENSESR-CLIENT'
    find_value = 'B40'
    new_group = 'group "RR-5-ENSESR_EBH"'
    new_description = 'Neighbor group for EVPN EBH Acess Leaf' 
    new_import_policy = 'IMPORT_RR-5-ENSESR_IRRW-EBH'
    b40_neighbors = extract_ring_neighbors(my_file_pd, start_key, find_value)
    add_b40_neighbors(new_description, b40_neighbors, new_import_policy, old_import_policy)


# In[15]:


def policy_bgp():
    print ('#--------------------------------------------------')
    print ('# New Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure router bgp')
    print ('        policy-options')
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


def policy_remove():
    print ('#--------------------------------------------------')
    print ('# Remove Policy Configuration')
    print ('#--------------------------------------------------')
    print('/configure route policy-options')
    print ('            begin')
    print ('            {} no {}'.format(cmty_string[0],cmty_member ))
    print ('                no {}'.format(cmty_string[0] ))
    print ('            exit')
    print ('            commit')
    print ('        exit all')
    print('#--------------------------------------------------')
    print('## Cleaning LLD 1.2.1 policies ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure route policy-options')
    print('  begin')
    print('    no policy-statement "LABEL_LOOPBACK0"')
    print('    no policy-statement "EXPORT_RR-5-PEER"')
    print('    no policy-statement "IMPORT_RR-5-PEER"')
    print('    no policy-statement "EXPORT_RR-5-ENSESR"')
    print('    no policy-statement "IMPORT_RR-5-ENSESR"')
    print('    no policy-statement "EXPORT_RR-5-ENSESR-CLIENT"')
    print('    no policy-statement "IMPORT_RR-5-ENSESR-CLIENT"')
    print('  commit')
    print('exit all')
    print('')
    print('#--------------------------------------------------')
    print('## Cleaning LLD 1.2.1 prefix lists and communities ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure route policy-options')
    print('  begin')
    print('    no prefix-list "Default-Routes"')
    print('    no prefix-list "PRFX_LOCAL_SYSTEM_ADDRESS"')
    print('  commit')
    print('exit all')  
    print('#--------------------------------------------------')
    print('# Cleaning LLD 1.2.1 BGP groups ... ')
    print('#--------------------------------------------------')
    print('')
    print('/configure router bgp')
    print('    group "RR-5-ENSESR-CLIENT" shutdown')
    print('    no group "RR-5-ENSESR-CLIENT"')
    print('    group "RR-5-PEER" shutdown')
    print('    no group "RR-5-PEER"')
    print('    group "RR-5-ENSESR" shutdown')
    print('    no group "RR-5-ENSESR"')
    print('        exit all')


# In[16]:


# Create a function to print all the required bof routes to be added and deleted
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


# In[17]:


def policy_RR_5_ENSESR_IRRW_CSR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-CSR"')
    print ('                description "EXPORT ROUTES TO RING CSRS"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-CSR"')
    print ('                description "IMPORT ROUTES FROM RING CSRS"')
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
    print ('                    description "IMPORT EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
#############################################################
def policy_RR_5_ENSESR_IRRW_EBH():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-EBH"')
    print ('                description "EXPORT ROUTES TO EBH AL"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-EBH"')
    print ('                description "IMPORT ROUTES FROM EBH AL"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
####################################################################
def policy_RR_5_ENSESR_IRRW_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-IRR"')
    print ('                description "EXPORT ROUTES TO PEER IRR"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-IRR"')
    print ('                description "IMPORT ROUTES FROM PEER IRR"')
    print ('                entry 10')
    print ('                    description "PREVENT LOOPBACK FROM REFLECTING BACK"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')

####################################################################
def policy_RR_5_ENSESR_IRRW_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRW-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRW-SPOKE"')
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
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
    print ('                    description "IMPORT EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')
####################################################################
#################### RING EAST      ###########################
####################################################################

def policy_RR_5_ENSESR_IRRE_CSR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-CSR"')
    print ('                description "EXPORT ROUTES TO RING CSRS"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-CSR"')
    print ('                description "IMPORT ROUTES FROM RING CSRS"')
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
    print ('                    description "IMPORT EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')


########################################################################
def policy_RR_5_ENSESR_IRRE_EBH():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-EBH"')
    print ('                description "EXPORT ROUTES TO EBH AL"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-EBH"')
    print ('                description "IMPORT ROUTES FROM EBH AL"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')

##############################################################################
def policy_RR_5_ENSESR_IRRE_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-IRR"')
    print ('                description "EXPORT ROUTES TO PEER IRR"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-IRR"')
    print ('                description "IMPORT ROUTES FROM PEER IRR"')
    print ('                entry 10')
    print ('                    description "PREVENT LOOPBACK FROM REFLECTING BACK"')
    print ('                    from')
    print ('                        protocol bgp-label')
    print ('                        prefix-list "PRFX_GLOBAL_LOOPBACK"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')

#########################################################################
def policy_RR_5_ENSESR_IRRE_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_IRRE-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_IRRE-SPOKE"')
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
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
    print ('                    description "IMPORT EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')


######################################################################################
#################################### RING NODE      ##################################
######################################################################################
def policy_RR_5_ENSESR_IRR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "EXPORT ROUTES TO IRRS"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-IRR"')
    print ('                description "IMPORT ROUTES FROM IRRS"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')

###########################################################################################

def policy_RR_5_ENSESR_SPOKE():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR_CSR-SPOKE"')
    print ('                description "EXPORT ROUTES TO SPOKE CSRS"')
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
    print ('                        protocol evpn-ifl')
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
    print ('                    description "PROPAGATE EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR_CSR-SPOKE"')
    print ('                description "IMPORT ROUTES FROM SPOKE CSRS"')
    print ('                entry 5')
    print ('                    description "DROP DEFAULT ROUTE"')
    print ('                    from')
    print ('                        prefix-list "PRFX_DEFAULT"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                entry 10')
    print ('                    description "IMPORT LEARNED BGP LABELS"')
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
    print ('                    description "IMPORT LEARNED EVPN ROUTES"')
    print ('                    from')
    print ('                        evpn-type 5')
    print ('                        family evpn')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')

###########################################################################################

def policy_RR_5_ENSESR_CSR():
    print ('        policy-options')
    print ('            begin')
    print ('            policy-statement "EXPORT_RR-5-ENSESR-CLIENT"')
    print ('                entry 10')
    print ('                    description "SEND MY LOOPBACK LABEL WITH SID"')
    print ('                    from')
    print ('                        prefix-list "PRFX_LOCAL_SYSTEM_ADDRESS"')
    print ('                    exit')
    print ('                    to')
    print ('                        protocol bgp-label')
    print ('                    exit')
    print ('                    action accept')
    print ('                        next-hop-self')
    print ('                        aigp-metric igp')
    print ('                    exit')
    print ('                exit')
    print ('                entry 20')
    print ('                    description "PROPAGATE CONNECTED ROUTES"')
    print ('                    from')
    print ('                        protocol direct')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 30')
    print ('                    description "PROPAGATE STATIC ROUTES"')
    print ('                    from')
    print ('                        protocol static')
    print ('                    exit')
    print ('                    action accept')
    print ('                    exit')
    print ('                exit')
    print ('                entry 40')
    print ('                    from')
    print ('                        prefix-list "Default-Routes"')
    print ('                    exit')
    print ('                    action drop')
    print ('                    exit')
    print ('                exit')
    print ('                default-action drop')
    print ('                exit')
    print ('            exit')
    print ('            policy-statement "IMPORT_RR-5-ENSESR-CLIENT"')
    print ('                default-action accept')
    print ('                exit')
    print ('            exit')
    print ('            commit')
    print ('        exit')


# In[18]:


def site_int():
    # B40 01 and 02 file for isis metric and bgp neighbor to a new group and delete neighbor from existing group.
    #print(b40facinginterface)
    print('########### Following info is Just to verify the interface and  system info ############')
    print('# System Name: {}", "system ip: {}",  '.format(name, system_ip))
    print('########################################################################################')
    print('')
    print('#### PLEASE LOGIN TO THE ROUTER USING point to point ip address, so as not to loose the connectivity when BGP is down. #####')
    print('/show system rollback')
    print('/admin rollback save comment "Pre-update Checkpoint"')
    print('')
    if my_file_pd['config'][ecmp].to_string() != 2:
        print('#--------------------------------------------------')
        print("# This router has ecmp value of 2, please change it to ecmp 1")
        print('#--------------------------------------------------')
        print('/configure router ecmp 1')
    print('#--------------------------------------------------')
    print('# New Interface Configuration')
    print('#--------------------------------------------------')
    print('')
    for interface_desc, description in metric_interface.items():
        print('/configure router isis 5 {} level 1 metric 1000000'.format(interface_desc))
    print('')
    print('/configure router interface "system" bfd 100 receive 100 multiplier 3')
    print('')
    print('#--------------------------------------------------')
    print('# Update ISIS 5 overload timout')
    print('#--------------------------------------------------')
    print('')    
    print('/configure router isis 5 overload-on-boot timeout 180')
    print('/configure port 1/1/24 ethernet speed 1000')
    print('')
    #print('/configure router bgp shutdown')
    #print('/configure router no bgp')
    #print(b40_name
    


# In[20]:


def new_qos():
    print('#--------------------------------------------------')
    print('# New QOS Configuration')
    print('#--------------------------------------------------')
    print('/configure qos')
    print('        port-qos-policy "40012" create')
    print('            description "eNSE SR Network Port QOS Policy"')
    print('            queue "1" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 24.00')
    print('                exit')
    print('            exit')
    print('            queue "2" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 3.00')
    print('                exit')
    print('            exit')
    print('            queue "3" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 1.00')
    print('                exit')
    print('            exit')
    print('            queue "4" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 3.00')
    print('                exit')
    print('            exit')
    print('            queue "5" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 8.00')
    print('                exit')
    print('            exit')
    print('            queue "6" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 55.00')
    print('                exit')
    print('            exit')
    print('            queue "7" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 5.00')
    print('                exit')
    print('            exit')
    print('            queue "8" create')
    print('                scheduler-mode wfq')
    print('                    percent-rate 100.00 cir 1.00')
    print('                exit')
    print('            exit')
    print('        exit all')


# In[21]:


# B40 group change and check interface to 1000000

def b40_01_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group ONLY after adding the bgp on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    #print ('/configure router isis 5 interface " level 1 metric 1000000
    print ('If the above interface level 1 metric is not 1000000 then change it to 1000000')


def b40_02_changes_ixre(system_ip, name):
    print ('###Remove neighbor from 121 bgp group after you have brought up 135 BGP neigh on B40-01 and 02')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# B40 group change and check interface to 1000000

def b40_01_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-01     "')
    print ('#--------------------------------------------------')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')


def b40_02_rollback_ixre(system_ip, name):
    print ('')
    print ('')
    print ('')
    print ('###################################################')
    print ('#     ROLLBACK FOR B40-02     "')
    print ('#--------------------------------------------------')
    print ('/configure router bgp group "RR-5-ENSESR_IRR" neighbor {} shutdown'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR_IRR" no neighbor {}'.format(system_ip))
    print ('exit all')
    print ('')
    print ('###Add neighbor to 135 bgp group')
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {}'.format(system_ip))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} description "iBGP-TO-{}"'.format(system_ip, name))
    print ('/configure router bgp group "RR-5-ENSESR" neighbor {} authentication-key "eNSEbgp"'.format(system_ip))
    print ('exit all')
    print ('')
    print ('#--------------------------------------------------')
    print ('# Check for the routers interface metric under ISIS 5"')
    print ('#--------------------------------------------------')
    print ('admin display-config | match "{}" context all'.format(name))
    print ('/show router isis 5 interface | match "site interface"')
    print ('If the interface level 1 metric is not 1000000 then change it to 1000000')


# In[22]:


# Post check ping check script / 
def pre_post_b40():
    print ('')
    print ('#--------------------------------------------------')
    print ('# Local IXRE post checks "')
    print ('#--------------------------------------------------')
    print ('show service sap-using')
    print ('show port A/gnss')
    print ('show system ptp port')
    print ('show router 1 interface')
    print ('show router 4 interface')
    print ('show router policy')
    print ('show router bgp summary')
    print ('')
    print ('#--------------------------------------------------')
    print ('# B40 post checks for pinging CSR interfaces from B40-01 and 02"')
    print ('#--------------------------------------------------')
    print('\show router bgp summary')
    for ran in vprn1_ip:
        print('ping router-instance "RAN" {}'.format(ran.split('/', 1)[0][8:]))
    for mgm in vprn4_ip:
        print('ping router-instance "CELL_MGMT" {}'.format(mgm.split('/', 1)[0][8:]))


# In[25]:


def find_unnumbered_int(data):
    global found_interface
    group_start_idx = data[data['config'].str.contains('echo "Router')].index[0]
    group_end_idx = data[data['config'].str.contains('echo "MPLS Label')].index[0]

    found_interface = []
    found_unnumbered = False 

    # Loop through the DataFrame between start and end indices, from end to start
    for i in range(group_end_idx - 1, group_start_idx - 1, -1):
        line = data.at[i, 'config'].strip()
        if line.startswith('unnumbered'):
            found_unnumbered = True 
        elif found_unnumbered and line.startswith('interface'):
            found_port = line.split()[1]  # get the port
            found_interface.append(found_port)
            found_unnumbered = False  # reset flag

    if found_interface:
        print(f"Ports with unnumbered: {found_interface}")
    else:
        print("No unnumbered port found")

    return found_interface

# Call the function on your DataFrame
#scan_file()
#all_files()
#for items in path:
#    create_pd()
#    unnumbered_ports = find_unnumbered_int(my_file_pd)
#    print(f"Ports with unnumbered: {unnumbered_ports}")


# In[26]:


def main():
    global items
    global folder
    scan_file()
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
        # Find what kind of a node is it B40, Ring, Spoke
        policy_client = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-PEER"')].tolist() # east or west ring router but not B40
        policy_spoke = my_file_pd.index[my_file_pd['config'].str.contains ('group "RR-5-ENSESR"')].tolist() #--- These are spokes and CSR 
        is_B40 = my_file_pd.index[(my_file_pd['config'].str.fullmatch('import "IMPORT_RR-5-ENSESR-CLIENT"') & my_file_pd['config'].shift(-6).str.contains('description.*B40'))].tolist()
        # This following is to use invert operator to ensure there is no b40 in description.
        is_csr_spoke = my_file_pd.index[(my_file_pd['config'].str.fullmatch('import "IMPORT_RR-5-ENSESR-CLIENT"') & ~ my_file_pd['config'].shift(-6).str.contains('description.*B40', na=False))].tolist() 
        
        # Bool check
        nonb40_peer_exists = bool(policy_client)
        spoke_exists = bool(policy_spoke)
        b40_exists = bool(is_B40)
        csr_spoke = bool(is_csr_spoke)
   
        sys.stdout = open(folder + '/' + name +'_LLD135.cfg','w')
        create_pd()
        metric_int(my_file_pd)
        create_sa_pd()
        site_int()
        print('#--------------------------------------------------')
        print('#       Update BGP Policies and Groups        ')
        print('#--------------------------------------------------')              
        policy_bgp()
      
    #----------------------------------------------------------------------
        if b40_exists:        #and len(is_B40)>=1
                extract_b40_neighbors(my_file_pd) #group "RR-5-ENSESR_CSR" for ring node that IS B40
                
                if '01' in b40_name:
                    print("This is a West Node")
                    policy_RR_5_ENSESR_IRRW_EBH() # for ring b40 node
                    rr_5_ensesr_irrw_ebh()
                    if spoke_exists:
                        extract_neighbors(my_file_pd)
                        if len(spoke_bgp_neighbors) >=1 or len(csr_bgp_neighbors)>=1:
            #-----------------------------------------------------
                        if len(spoke_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRW_SPOKE() # for west spokes
                            RR_5_ENSESR_IRRW_SPOKE(spoke_bgp_neighbors) #group "RR-5-ENSESR_SPOKE" for spoke west neighbors
                        if len(csr_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRW_CSR() # policy for the CSR non spoke ixre
                            RR_5_ENSESR_IRRW_CSR(csr_bgp_neighbors) # group "RR-5-ENSESR_CSR" for non spoke csr neighbors

                    if nonb40_peer_exists: 
                        extract_ring_neighbors(my_file_pd)
                        policy_RR_5_ENSESR_IRRW_IRR() # for CSR that is not a spoke
                        rr_5_ensesr_csr_west() #group "RR-5-ENSESR_CSR" for east or west ring node NOT B40
                        
                    # B40-01 changes in a new file
                    sys.stdout = open(folder + '/' + name +'_B40-01.txt','w')
                    b40_01_changes_ixre(system_ip, name)
                    b40_01_rollback_ixre(system_ip, name)
                    
                    policy_remove()
                    
                else:
                    print("This is a East Node")
                    policy_RR_5_ENSESR_IRRE_EBH() # for ring b40 node
                    rr_5_ensesr_irre_ebh()

                    if spoke_exists:
                        extract_neighbors(my_file_pd)
                        if len(spoke_bgp_neighbors) >=1 or len(csr_bgp_neighbors)>=1:
                            print('/configure router bgp')
                            print('    group "RR-5-ENSESR" shutdown')
                            print('    no group "RR-5-ENSESR"')
                            print('exit all')
            #--------------------------------------------------------------------------------------------------
                        if len(spoke_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRE_SPOKE() # for East spokes
                            RR_5_ENSESR_IRRE_SPOKE(spoke_bgp_neighbors) #group "RR-5-ENSESR_SPOKE" for spoke East neighbors
                        if len(csr_bgp_neighbors)>=1:
                            policy_RR_5_ENSESR_IRRE_CSR() # policy for the CSR non spoke ixre
                            RR_5_ENSESR_IRRE_CSR(csr_bgp_neighbors) # group "RR-5-ENSESR_CSR" for non spoke csr neighbors

                    if nonb40_peer_exists: 
                        extract_ring_neighbors(my_file_pd)
                        policy_RR_5_ENSESR_IRRE_IRR() # for CSR that is not a spoke
                        rr_5_ensesr_csr_east() #group "RR-5-ENSESR_CSR" for east or west ring node NOT B40

                    policy_remove()


                    
                    # B40-02 changes in a new file
                    sys.stdout = open(folder + '/' + name +'_B40-02.txt','w')
                    b40_02_changes_ixre(system_ip, name)
                    b40_02_rollback_ixre(system_ip, name)
        
                # BOF config changes
                sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
                create_bof(old_statics)
    
        
                # Post checks file generation
                sys.stdout = open(folder + '/' + name +'_Post_Checks.txt','w')
                pre_post_b40()
                os.chdir("..")  # Move up one directory

    #---------------------------------------------------------------------------------------------------------
        else:
            

    # FROM group "RR-5-ENSESR" 121 TO group "RR-5-ENSESR_SPOKE" 135
            if csr_spoke:        #and len(is_csr_spoke)>=1
                policy_RR_5_ENSESR_SPOKE()
                del_rr_5_ensesr()
                extract_neighbors(my_file_pd) #group "RR-5-ENSESR" for spoke nodes on ring IRR
                rr_5_ensesr_spoke_IRR(spoke_bgp_neighbors)
            
    
    # FROM group "RR-5-ENSESR-CLIENT" 121 to group "RR-5-ENSESR_IRR" 135
            if spoke_exists:
                extract_spoke_neighbors(my_file_pd)
                policy_RR_5_ENSESR_IRR() # for ring node IRR() # policy for the CSR non spoke ixre	    
                del_rr_5_ensesr_IRR()
                rr_5_csr_end_spoke_IRR(csr_spoke_bgp_neighbors) # group "RR-5-ENSESR_CSR" for non spoke csr neighbors 
                               
        #----------------------------------------------------------------------------------------------------------
            policy_remove()
            # BOF config changes
            sys.stdout = open(folder + '/' + name +'_bof.cfg','w')
            create_bof(old_statics)
    
        
            # Post checks file generation
            sys.stdout = open(folder + '/' + name +'_Post_Checks.txt','w')
            pre_post_b40()
            os.chdir("..")  # Move up one directory
    
    #-------------------------------------------------------------------------------




if __name__ == "__main__":
    main()


# In[ ]:





# In[ ]:




