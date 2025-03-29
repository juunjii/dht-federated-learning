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
        self.finger_table = [None] * (int(ceil(log2(MAX_NODES))) + 1)
        self.finger_ids = [None] * (int(ceil(log2(MAX_NODES))) + 1)

        # Tracks current files used for training
        self.work= set()

        # Supernode information (for joining)
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port

        #model stored info
        self.weights = {}

        self.node_join()


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
    Reach the node responsible for the file
    '''
    def reach_destination(self, key):
        if not key or key < -1:
            return None
        # check if the accepted key range
        if self.pred_id < key <= self.node_id:
            return True
        
        # this is the case where part of the key range is reset back to 0
        if self.node_id < self.pred_id and (key > self.pred_id or key <= self.node_id):
            return True
        
        # Single node in network (no predecessors)
        if self.pred_id == self.node_id:
            return True
        
        return False


    '''
    Forward the data to appropriate node 

    Should return addrress of node to allow for recursive calls 
    '''
    def forward_data(self, key):
        for i in range(len(self.finger_ids) - 1, -1, -1):
            if self.finger_ids[i] is not None and self.pred_id < self.finger_ids[i] < key:
                return self.finger_table[i]
        return self.succ
    
    ''' 
    Train model when data reaches node;
    Stores trained weights, V and W for later retrieval
    '''
    def train(self, fname):
        model = mlp()
        if model.init_training_random(fname, _k=26, _h=20):
            V, W = model.get_weights()
            self.weights[fname] = WeightMatrices(V=V.tolist(), W=W.tolist())

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
            print(f"Failed to connect to node (in connect_to_node) {host}:{port} - {e}")
            return None, None  
    
    def unpack_add(self, add):
        if not add:
            return None
        host, port = add

        return host, port

    '''
    Place input ML data (filename) into the network;
    Recursively finds the destination node
    '''
    def put_data(self, fname):
        # Hash fname to numerical key value
        key = self.hash_filename(fname)
        
        # Reach destination node
        if self.reach_destination(key):
            print(f"Node {self.node_id} storing and training on file: {fname}")

            # Add to work set
            self.work.add(fname)
            Thread(target=self.train, args=(fname,)).start()
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

    def get_model(self, fname):
        '''return a model from a node from an input dataset (filename)'''
        key = self.hash_filename(fname)

        if self.reach_destination(key):
            if fname in self.weights:
                return self.weights[fname]
            if fname in self.work:
                # must wait for completion
                return 'wait'
            #  not found
            return '404'
        
        node = self.forward_data(key)
        print(f"Node {self.node_id} forwarding file {fname} to node at {node}")

        host, port = self.unpack_add(node)
        client, transport = self.connect_to_node(host, port)

        if client and transport:
            try:
                client.get_model(fname)  
            # Ensures that connection would be closed
            finally: 
                transport.close() 
            
    def fix_fingers(self):
        '''Makes a node fix its finger table'''
        for i in range(len(self.finger_table)):
            # calculate key, update finger table and ids
            key = (self.node_id + 2**i) % MAX_NODES
            self.finger_ids[i] = key
            self.finger_table[i] = self.forward_data(key)
        
        # no successor
        if not self.succ:
            return

        host, port = self.unpack_add(self.succ)
        client, transport = self.connect_to_node(host, port)
        
        if client and transport:
            try:
                client.fix_fingers()
            finally:
                transport.close()
                
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
            
    def node_join(self):
        '''compute node joins the network'''
        # setup connection with supernode
        transport = TSocket.TSocket(self.supernode_host, self.supernode_port)
        transport = TTransport.TBufferedTransport(transport)
        protocol = TBinaryProtocol.TBinaryProtocol(transport)
        client = super.Client(protocol)
        transport.open()
        
        self.node_id = client.request_join(self.port)
        if self.node_id == -1:
            print("Error requesting join from super")
            return -1

        # get the node that represents the join position
        node = client.get_node()

        if not node:
            transport.close()
            return
        
        if node.ip == None:
            print("First node in network")
            self.pred = (self.host, self.port)
            self.succ = (self.host, self.port)
            self.pred_id = self.node_id
            self.succ_id = self.node_id
            client.confirm_join(self.node_id)
            transport.close()
            return
        
        # make connection with join position node
        # host, port = self.unpack_add(node)
        client2, transport2 = self.connect_to_node(node.ip, node.port)
        if client2 and transport2:
            try:
                # set internal values to join
                # TODO: Figure out what the error with getpred/succ is, add code to set pred_id and succ_id
                # self.succ_id = client2.find_successor(self.node_id)
                # self.succ = self.get_node_addreess(self.succ_id)
                # self.pred_id = client2.find_predecessor()
                # self.pred = self.get_node_addreess(self.pred)
                self.succ = client2.get_successor()
                self.pred = client2.get_predecessor()
                self.pred_id = self.get_node_id(self.pred)
                self.succ_id = self.get_node_id(self.succ)
                self.fix_fingers()
                client.confirm_join(self.node_id)
            finally:
                transport2.close()
        transport.close()
    
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
    
    def get_responsible_key_range(self):
        """Get the range of keys this node is responsible for"""
        if self.predecessor_id is None:
            return f"[0-{MAX_NODES-1}]"
            
        # Keys from (predecessor, self]
        if self.predecessor_id < self.node_id:
            return f"({self.pred_id}-{self.node_id}]"
        else:  # Wrapping around
            return f"({self.pred_id}-{MAX_NODES-1}] and [0-{self.node_id}]"
        
    def print_info(self):
        '''prints node info'''
        
        print("Network connection info")
        print("Predecessor: ", self.pred)
        print("Successor: ", self.succ)
        print("Finger Table:")
        print("i", "Node", "ID")
        for i in range(len(self.finger_table)):
            print(i, self.finger_table[i], self.finger_ids[i])
        print(f"Responsible for keys: {self.get_responsible_key_range()}\n")
        print("Hashing info")
        print("Node ID: ", self.node_id)
        print("Files: ")
        for file in self.weights.keys():
            print(file, ", ")
    
    def get_successor(self):
        """Returns the successor node"""
        return self.succ

    def get_predecessor(self):
        """Returns the predecessor node"""
        return self.pred

def main():
    if len(sys.argv) != 5:
        print("Usage: python3 compute_node.py <host> <port> <supernode_host> <supernode_port>")
        sys.exit(1)

    host= sys.argv[1]
    port = int(sys.argv[2])
    supernode_host = sys.argv[3]
    supernode_port = int(sys.argv[4])

    handler = ComputeNodeHandler(host, port, supernode_host=supernode_host, supernode_port=supernode_port)
    processor = compute.Processor(handler)
    transport = TSocket.TServerSocket(host=host, port=port)
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolFactory()

    server = TServer.TThreadedServer(processor, transport, tfactory, pfactory)

    print(f"Starting Compute Node on host {host} and port {port}...")
    server.serve()

if __name__ == "__main__":
    try:
        main()
    except Thrift.TException as tx:
        print('%s' % tx.message)

