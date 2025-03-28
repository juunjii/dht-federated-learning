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
        self.pred = None
        self.pred_id = None
        self.succ = None
        self.succ_id = None
        self.finger_table = [None] * int(ceil(log2(MAX_NODES))) 
        self.finger_ids = [None] * int(ceil(log2(MAX_NODES)))

        # Tracks current files used for training
        self.work= set()

        # Supernode information (for joining)
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port


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
        
        for i in range(n, 0, -1):
            # Forward to FT[i] <=k and FT[i+1] > k
            if self.finger_table[i] and self.is_between(self.finger_ids[i], self.node_id, key):
                return self.finger_table[i] # (host, port) of node
        
        # Return own successor
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
        pass

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
            

