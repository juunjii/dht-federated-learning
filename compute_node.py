import sys
import time
import random
import glob
from threading import Thread
import os 

sys.path.append('gen-py')
sys.path.insert(0, glob.glob('../thrift-0.19.0/lib/py/build/lib*')[0])

from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer


from compute import compute
from compute.ttypes import WeightMatrices
from super import super 
from ML import *
from math import ceil, log2

# Macro for maximum network capacity 
MAX_NODES = 10


class ComputeNodeHandler:
    def __init__(self, host, port, supernode_host='localhost', supernode_port=9090):
        # Connection information to other nodes in network
        self.host = host
        self.port = port
        self.addr = (host, port)
        self.node_id = None

        # Finger table variables
        self.pred = None # tuple 
        self.pred_id = None
        self.succ = None # tuple
        self.succ_id = None
        self.finger_table = [None] * int(ceil(log2(MAX_NODES))) 
        self.finger_ids = [None] * int(ceil(log2(MAX_NODES)))

        # Tracks current files used for training
        self.work= set()

        # Stores local models for client query
        self.models = {}

        # Supernode information (for joining)
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port
    
    '''
    Connect to another node in the network
    '''
    def connect_to_supernode(self):
        try:
            transport = TSocket.TSocket(self.supernode_host, self.supernode_port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = super.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {self.supernode_host}:{self.supernode_port} - {e}")
            return None, None  
    
    '''
    Find the successor for specified node
    '''
    def find_successor(self, node_id):
        if not node_id:
            return -1

        # If node id is between own node id and successor id 
        if self.is_between(node_id, self.node_id, self.succ_id):
            return self.succ_id
        
        # Find the closest preceding node
        closest = self.get_closest_finger_entry(node_id)
        
        # No better routing option available 
        if closest == self.addr:
            return self.succ_id
    
    '''
    Get current node's predecessor
    '''
    def get_predecessor(self):
        return self.pred
    
    '''
    Return current node's id
    '''
    def get_id(self):
        return self.node_id
    
    
    '''
    Get corresponding address (host, port) of node by querying the network
    '''
    def get_node_addreess(self, node_id):
        if not node_id:
            return -1

        if node_id == self.node_id:
            return self.addr
            
        if node_id == self.succ_id:
            return self.succ
            
        if node_id == self.pred_id:
            return self.pred
            
        # Check finger table
        for i, id in enumerate(self.finger_ids):
            if id == node_id:
                return self.finger_table[i]
        
        # Query the network to get successor info
        succ_id = self.find_successor(node_id)

        # Found node 
        if succ_id == node_id:
            succ_ip, succ_port = self.unpack_add(self.succ)
            
            client, transport = self.connect_to_node(succ_ip, succ_port)
            if client and transport:
                try:
                    return client.get_predecessor()
                # Ensures that connection would be closed
                finally: 
                    transport.close() 
        
        return self.successor  

    '''
    Nodes join the network, they will need to contact  the supernode, initialize their own 
    predecessors, successors, and finger tables, and update existing nodes in the network.  
    '''
    def node_join(self):
        client, transport = self.connect_to_supernode()
        if client and transport:
            try:
                self.node_id = super.request_join(self.port)
                print(f"Node joins with ID: {self.node_id}")
                
                connection_point = super.get_node() # Node(ip, port)
                conn_ip = connection_point.ip
                conn_port = connection_point.port 
                print(f"Node joins with connection point: {connection_point.ip, connection_point.port}")
                
                # Empty network
                if conn_ip == None or conn_port == None:
                    # Initialize successor as self
                    self.succ = self.addr
                    self.succ_id = self.node_id
                    
                    # Initialize predecessor as self
                    self.pred = self.addr
                    self.pred_id = self.node_id
                    
                    # Initialize finger table to point to self
                    for i in range(len(self.finger_table)):
                        self.finger_table[i] = self.addr
                        self.finger_ids[i] = self.node_id

                # Node joins via connection point 
                else:
                    client, transport = self.connect_to_node(conn_ip, conn_port)
                    if client and transport:
                        try:
                            # Find successor for new node 
                            succ_id = client.find_successor(self.node_id)
                            succ_add = self.get_node_addreess(succ_id)

                            # Update successor
                            self.succ_id = succ_id
                            self.succ = succ_add

                            # Update finger table with successor (1st entry)
                            self.finger_ids[0] = succ_id
                            self.finger_table[0] = succ_add

                            # Update own finger table 
                            self.update_finger_table(client)

                            # Update other finger tables
                            self.update_other_finger_tables()

                            # Set predecessor



                        # Ensures that connection would be closed
                        finally: 
                            transport.close() 




            # Ensures that connection would be closed
            finally: 
                transport.close() 

    ''' 
    Update finger table of connection point 
    '''
    def update_finger_table(self, node):
        if not node:
            return -1

        # Number of entries
        n = int(ceil(log2(MAX_NODES)))

        # Update entries - start from 1 to (MAX_NODES - 1)
        for i in range(1, n + 1):
            entry_val = (self.node_id + 2**(i-1)) % MAX_NODES

            # Finger table knows responsible nodes 
            if self.is_between(entry_val, self.node_id, self.succ_id):
                self.finger_table[i] = self.succ
                self.finger_ids[i] = self.succ_id
            else:
                # Node find its correct successor
                succ_id = node.find_successor(entry_val)
                succ_add = self.get_node_addreess(succ_id)
                self.finger_ids[i] = succ_id
                self.finger_table[i] = succ_add

    '''
    Given node address, return the respective node id
    '''
    def get_node_id(self, address):
        if address == self.addr:
            return self.node_id
            
        if address == self.successor:
            return self.successor_id
            
        if address == self.predecessor:
            return self.predecessor_id
            
        # Check finger table
        for i, addr in enumerate(self.finger_table):
            if addr == address:
                return self.finger_ids[i]
        
        # Address not in finger table 
        # Query the network to get node id
        try:
            ip, port = self.unpack_add(address)
            
            client, transport = self.connect_to_node(ip, port)
            if client and transport:
                try:
                    return client.get_id()
                # Ensures that connection would be closed
                finally: 
                    transport.close() 
        except:
            print(f"Error: Failed to find node id for address - {address}")
            return -1


    '''
    Find corresponing predecessor for given node in network
    '''
    def find_predecessor(self, node_id):
        # Sanitize
        if not node_id:
            return -1
        
        # One node in network
        if self.succ_id == self.node_id:
            return self.addr
        
        curr_id = self.node_id
        curr_addr = self.addr

        closest_entry = self.get_closest_finger_entry(node_id)
        
        # Continue searching until we find a node where input node is between it and its closest preceding node
        while not self.is_between(node_id, curr_id, self.get_node_id(closest_entry)):
            # If we're still at the current node
            if curr_addr == self.addr:  
                # Move to the closest preceding finger entry
                curr_addr = self.get_closest_finger_entry(node_id)
                curr_id = self.get_node_id(curr_addr)
            # Connect to the remote node and ask for its closest preceding finger
            else:
                ip, port = self.unpack_add(curr_addr)
                client, transport = self.connect_to_node(ip, port)
                if client and transport:
                    try:
                        closest = client.get_closest_finger_entry(node_id)
                        # Prevent infinite loop if cannot find suitable node
                        if closest == curr_addr: 
                            break
                        # Move to the newly found closest node
                        curr_addr = closest
                        curr_id = self.get_node_id(curr_addr)
                    # Ensures that connection would be closed
                    finally: 
                        transport.close() 
        
        return curr_addr
    
    def fix_fingers(self):
        n = int(ceil(log2(MAX_NODES)))

        for i in range(1, n + 1):
            e = (self.node_id + 2**(i - 1)) % MAX_NODES

            # Get successor info
            succ_id = self.find_successor(e)
            succ_add = self.get_node_addreess(succ_id)

            # Update finger table with successor
            self.finger_table[i] = succ_add
            self.finger_ids[i] = succ_id

            # Recursively fix finger tables by contacting successor
            if self.succ != self.addr:
                ip, port = self.unpack_add(self.succ)
                client, transport = self.connect_to_node(ip, port)
                if client and transport:
                    try:
                        client.fix_fingers()
                    # Ensures that connection would be closed
                    finally: 
                        transport.close() 

            
    '''
    Update existing nodes' finger tables in the network 
    when new node joins network
    '''
    def update_other_finger_tables(self):
        # Number of entries
        n = int(ceil(log2(MAX_NODES)))

        # Update entries - start from 1 to (MAX_NODES - 1)
        for i in range(1, n + 1):
            # Get previous entry
            pred = (self.node_id - 2**(i-1)) % MAX_NODES

            # Find the address of predecessor
            pred_addr = self.find_predecessor(pred)
            
            # Update predecessor's finger table (invalid when new node join)
            if pred_addr != self.addr:  
                ip, port = self.unpack_add(pred_addr)
                client, transport = self.connect_to_node(ip, port)
                if client and transport:
                    try:
                       client.fix_fingers()
                    # Ensures that connection would be closed
                    finally: 
                        transport.close() 

    '''
    Hash fname to numerical key value 
    Key value: 0 - (MAX_NODES -1)
    '''
    def hash_filename(self, fname):
        # Sanitize
        if not fname:
            return None

        return hash(fname) % MAX_NODES
    
    '''
    Using the ID of their predecessor, nodes will accept keys with values 
    greater than their predecessor’s ID and less than or equal to their own ID
    '''
    def is_between(self, key, id1, id2):
        # Sanitize
        if not key or key < -1:
            return None
        
        if id1 < id2:
            return id1 < key <= id2
        else: # Wrap around when range crosses (MAX_NODES -1)
            return id1 < key <= MAX_NODES-1 or 0 <= key <= id2


    '''
    Reach the node responsible for the file
    '''
    def reach_destination(self, key):
        # Sanitize
        if not key or key < -1:
            return None
         
        # Single node in network (no predecessors)
        if self.pred_id == self.node_id:
            return True

        return self.is_between(key, self.pred_id, self.node_id)

    '''
    Get closest finger preceding ID
    '''
    def get_closest_finger_entry(self, key):
        
        # Total entries
        n = int(ceil(log2(MAX_NODES))) 
        
        # Ensure lookup is faster by starting from bottom entries
        for i in range(n, 0, -1):
            # Valid forward if FT[i] <=k and FT[i+1] > k
            # If the i-th finger table entry falls in the interval (self.node_id, key]
            if self.finger_table[i] and self.is_between(self.finger_ids[i], self.node_id, key):
                return self.finger_table[i] # (host, port) of node
        
        # No suitable entry found, return own successor
        return self.addr

    '''
    Forward the data to next node until appropriate node is found 

    Should return addrress - (host, port) of node to allow for recursive calls 
    '''
    def forward_data(self, key):
        # Forward to closest successor node (node_id < key <= succ_id) in finger table
        if self.is_between(key, self.node_id, self.succ_id):
            return self.succ
        
        closest_succ = self.get_closest_finger_entry(key)
        if closest_succ == self.addr: 
            return self.successor
        
        return closest_succ
        
    
    ''' 
    Train model when data reaches node;
    Stores trained weights, V and W for later retrieval
    '''
    def train(self, fname):
        try:
            model = mlp()

             # Initialize model before training
            initialized_model = model.init_training_model(fname, _k = 26, _h =20)
            if (initialized_model == False):
                raise Exception(f"Model initialization failed with file {fname}")

            # Train
            training_error_rate = model.train(eta = 0.0001, epochs = 250)
            if (training_error_rate == -1):
                self.work.remove(fname)
                raise Exception("Model training failed!")
                
            print(f"Finished training {fname} with error rate: {training_error_rate}")

            # New weights
            trained_V, trained_W = model.get_weights()


            # Store local model 
            self.models[fname] = {
                'V': trained_V,
                'W': trained_W,
                'status': 'ready'
            }

            # Remove file from work set 
            self.work.remove(fname)


        except Exception as e:
            print(f"Exception in training thread: {e}")
            if fname in self.work:
                self.work.remove(fname)

    '''
    Connect to another node in the network
    '''
    def connect_to_node(self, host, port):
        try:
            transport = TSocket.TSocket(host, port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = compute.Client(protocol)
            transport.open()
            return client, transport  
        except Exception as e:
            print(f"Failed to connect to node {host}:{port} - {e}")
            return None, None  
    
    '''
    Unpack the tuple - self.add = (host, port)
    '''
    def unpack_add(self, add):
        # Sanitize
        if not add:
            return None

        host, port = add

        return host, port

    '''
    Place input ML data (filename) into the network;
    Recursively finds the destination node
    '''
    def put_data(self, fname):
        # Hash fname to numerical key value (0 - MAX_NODES -1)
        key = self.hash_filename(fname)
        
        # Reach destination node
        if self.reach_destination(key):
            print(f"Node {self.node_id} storing and training on file: {fname}")

            # Add to work set
            self.work.add(fname)
            # Start training
            Thread(target=self.train, args=(fname)).start()
        # Continue forwarding 
        else:
            # Return address of node (self.add = (host, port)
            node = self.forward_data(key)
            print(f"Node {self.node_id} forwarding file {fname} to node at {node}")

            host, port = self.unpack_add(node)
            client, transport = self.connect_to_node(host, port)

            if client and transport:
                try:
                    client.put_data(fname)  
                # Ensures that connection would be closed
                finally: 
                    transport.close() 
            

