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
from compute.ttypes import WeightMatrices, NodeInfo
from supernode import super 
import socket
from ML import *
from math import ceil, log2


class ComputeNodeHandler:
    def __init__(self, host, port, supernode_host, supernode_port):
        # Connection information to other nodes in network
        self.host = host
        self.port = port
        self.addr = (host, port)
        self.node_id = None

        # Supernode information (for joining)
        self.supernode_host = supernode_host
        self.supernode_port = supernode_port

        # Get MAX_NODES value from supernode
        self.max_nodes = self.get_max_nodes_from_supernode()

        # Finger table variables
        self.pred = None # tuple 
        self.pred_id = None
        self.succ = None # tuple
        self.succ_id = None
        self.finger_table = [None] * int(ceil(log2(self.max_nodes)) + 2) 
        self.finger_ids = [None] * int(ceil(log2(self.max_nodes))+ 2)

        # Tracks current files used for training
        self.work= set()

        # Stores local models for client query
        self.models = {}

        # Tracks data path through the network 
        self.data_path = {}

     


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
        
    def get_max_nodes_from_supernode(self):
        # Connect to supernode to get max_nodes value
        client, transport = self.connect_to_supernode()
        if client is None or transport is None:
            print("Failed to connect to supernode, using default MAX_NODES=5")
            return 5
        
        try:
            max_nodes = client.get_max_nodes()
            print(f"Retrieved MAX_NODES={max_nodes} from supernode")
            return max_nodes
        except Exception as e:
            print(f"Error getting max_nodes from supernode: {e}")
            return 5 # Default fallback value
        finally:
            if transport is not None:
                transport.close()
    
    '''
    Find the successor for specified node
    '''
    def find_successor(self, node_id):
        # If we're the only node in the network
        if self.succ_id == self.node_id:
            return NodeInfo(node_id=self.node_id, node_addr=str(self.addr))
        
        # Check if the ID is between this node and its successor
        if self.is_between(node_id, self.node_id, self.succ_id):
            return NodeInfo(node_id=self.succ_id, node_addr=str(self.succ))
        
        # Find the closest preceding node from finger table
        closest = self.get_closest_finger_entry(node_id)
        
        # If we are the closest preceding node, return our successor
        if closest == self.addr:
            return NodeInfo(node_id=self.succ_id, node_addr=str(self.succ))
        
        # Forward the request to the closest preceding node
        ip, port = self.unpack_add(closest)
        client, transport = self.connect_to_node(ip, port)
        
        if client and transport:
            try:
                # Call find_successor on the closest preceding node
                result = client.find_successor(node_id)
                return result
            except Exception as e:
                print(f"Error forwarding find_successor to {ip}:{port}: {e}")
                # Fall back to our own successor if the forward fails
                return NodeInfo(node_id=self.succ_id, node_addr=str(self.succ))
            finally:
                transport.close()
        
        # If connection fails, return our successor as fallback
        return NodeInfo(node_id=self.succ_id, node_addr=str(self.succ))

    '''
    Get current node's predecessor
    '''
    def get_predecessor(self):
        if self.pred is None:
        # Returns empty/default values
            return NodeInfo(node_id=-1, node_addr="")
    
        # Returns predecessor's ID and address
        return NodeInfo(node_id=self.pred_id, node_addr=str(self.pred))
    
    '''
    Return current node's id
    '''
    def get_id(self):
        return self.node_id
    
    
    '''
    Successor correctly updates its predecessor reference when new node joins network
    '''
    def update_predecessor(self, node_info):
        # Sanitize input 
        if node_info is None or node_info.node_id < 0 or not node_info.node_addr:
            return -1
        
        # Extract values from NodeInfo
        node_id = node_info.node_id
        address = eval(node_info.node_addr) if node_info.node_addr else None
        
        # Check if pred_id < node_id <= current node id
        between = self.is_between(node_id, self.pred_id, self.node_id)
        if self.pred is None or between:
            self.pred = address
            self.pred_id = node_id

    '''
    Nodes join the network, they will need to contact  the supernode, initialize their own 
    predecessors, successors, and finger tables, and update existing nodes in the network.  
    '''
    def node_join(self):
        # Connect to supernode to get ID and connection point
        super_client, super_transport = self.connect_to_supernode()
        if super_client is None or super_transport is None:
            print("Failed to connect to supernode")
            return
            
        try:
            # Get ID from supernode
            self.node_id = super_client.request_join(self.port)
            print(f"Node joins with ID: {self.node_id}")
            
            # Get connection point from supernode
            connection_point = super_client.get_node()
            conn_ip, conn_port = connection_point.ip, connection_point.port
            print(f"Received connection point: {conn_ip}:{conn_port}")
            
            # Check if this is the first node (no connection point returned)
            if conn_ip is None or conn_port is None:
                print("First node in network, initializing as sole node")
                self.succ = self.addr
                self.succ_id = self.node_id
                self.pred = self.addr
                self.pred_id = self.node_id
                
                # Initialize finger table to point to self
                for i in range(1, len(self.finger_table)):
                    self.finger_table[i] = self.addr
                    self.finger_ids[i] = self.node_id
                    
                super_client.confirm_join(self.node_id)
                return
                
            # Join existing network through connection point
            print(f"Connecting to network via connection point: {conn_ip}:{conn_port}")
            node_client, node_transport = self.connect_to_node(conn_ip, conn_port)
            
            if node_client is None or node_transport is None:
                print(f"Failed to connect to network via connection point: {conn_ip}:{conn_port}")
                return
                
            try:
                # Find successor for this node
                succ_info = node_client.find_successor(self.node_id)
                
                if succ_info is None:
                    print("Error: Received None as successor info")
                    return
                
                self.succ_id = succ_info.node_id
                self.succ = eval(succ_info.node_addr)
                
                # Set first finger table entry
                self.finger_ids[1] = self.succ_id
                self.finger_table[1] = self.succ
                
                # Get predecessor from successor
                succ_ip, succ_port = self.unpack_add(self.succ)
                succ_client, succ_transport = self.connect_to_node(succ_ip, succ_port)
                if succ_client and succ_transport:
                    try:
                        pred_info = succ_client.get_predecessor()
                        if pred_info and pred_info.node_id >= 0:
                            self.pred_id = pred_info.node_id
                            self.pred = eval(pred_info.node_addr) if pred_info.node_addr else None
                        
                        # Update successor's predecessor to this node
                        succ_client.update_predecessor(NodeInfo(
                            node_id=self.node_id, 
                            node_addr=str(self.addr)
                        ))
                    finally:
                        succ_transport.close()
                
                # Update finger table
                self.update_finger_table(node_client)
                
                # Update others
                self.update_other_finger_tables()
                
                # Confirm join with supernode
                super_client.confirm_join(self.node_id)

                print("\n=== NODE JOIN COMPLETED ===")
                print(self.print_info())
                
            finally:
                node_transport.close()
        finally:
            super_transport.close()
    ''' 
    Update finger table of connection point 
    '''
    def update_finger_table(self, node):
        n = int(ceil(log2(self.max_nodes)))
    
        print(f"Node {self.node_id} updating finger table with {n} entries")
        
        # Start with index 1 (the first finger is always the successor)
        for i in range(1, n + 1):
            # Calculate the ID for this finger entry
            start = (self.node_id + 2**(i-1)) % self.max_nodes
            print(f"Entry {i}: Looking for successor of key {start}")
            
            # Query the network for the successor of this ID
            try:
                succ_info = node.find_successor(start)
                if succ_info and succ_info.node_id >= 0:
                    succ_id = succ_info.node_id
                    succ_add = eval(succ_info.node_addr) if succ_info.node_addr else None
                    
                    if succ_add:
                        # Update finger table
                        self.finger_ids[i] = succ_id
                        self.finger_table[i] = succ_add
                        print(f"Updated entry {i} to node {succ_id} at {succ_add}")
            except Exception as e:
                print(f"Error updating finger table entry {i}: {e}")


    '''
    Given node address, return the respective node id
    '''
    def get_node_id(self, address):
        if address == self.addr:
            return self.node_id
            
        if address == self.succ:
            return self.succ_id
            
        if address == self.pred:
            return self.pred_id
            
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
        # One node in network
        if self.succ_id == self.node_id:
            return NodeInfo(node_id=self.node_id, node_addr=str(self.addr))
        
        curr_id = self.node_id
        curr_addr = self.addr

        closest_entry = self.get_closest_finger_entry(node_id)

        visited_nodes = set([curr_addr])
        
        # Continue searching until we find a node where input node is between it and its closest preceding node
        while not self.is_between(node_id, curr_id, self.get_node_id(closest_entry)):
           
            # If we're still at the current node
            if curr_addr == self.addr:  
                # Move to the closest preceding finger entry
                new_addr = self.get_closest_finger_entry(node_id)

                if new_addr == self.addr:
                    break
                
                curr_addr = new_addr
                curr_id = self.get_node_id(curr_addr)

            # Connect to the remote node and ask for its closest preceding finger
            else:
                ip, port = self.unpack_add(curr_addr)
                client, transport = self.connect_to_node(ip, port)
                if client and transport:
                    try:
                        closest = client.get_closest_finger_entry(node_id)
                        # Prevent infinite loop if cannot find suitable node
                        if closest == curr_addr or closest in visited_nodes: 
                            break
                        # Move to the newly found closest node
                        visited_nodes.add(closest)
                        curr_addr = closest
                        curr_id = self.get_node_id(curr_addr)
                    # Ensures that connection would be closed
                    finally: 
                        transport.close() 
        
        return NodeInfo(node_id=curr_id, node_addr=str(curr_addr))
    
    def fix_fingers(self):
        n = int(ceil(log2(self.max_nodes)))
        print(f"Node {self.node_id} fixing {n} finger table entries")

        for i in range(1, n + 1):
            e = (self.node_id + 2**(i - 1)) % self.max_nodes
            # Get successor info
            succ_info = self.find_successor(e)
            succ_id = succ_info.node_id
            succ_add = eval(succ_info.node_addr)
            
            # Update finger table with successor
            self.finger_table[i] = succ_add
            self.finger_ids[i] = succ_id

            # Only propagate to successor if not already visited
            if self.succ != self.addr and self.succ_id:
                print(f"Node {self.node_id} propagating fix_fingers to Node {self.succ_id}")
                ip, port = self.unpack_add(self.succ)
                client, transport = self.connect_to_node(ip, port)
                if client and transport:
                    try:
                        client.fix_fingers()
                    finally:
                        transport.close()

            
    '''
    Update existing nodes' finger tables in the network 
    when new node joins network
    '''
    def update_other_finger_tables(self):
        n = int(ceil(log2(self.max_nodes)))
        print(f"Node {self.node_id} updating finger tables of other nodes")
        
        # Find nodes that should point to us in their finger tables
        for i in range(1, n + 1):
            # Find node p whose i-th finger might be us
            # p is the node that precedes us by 2^(i-1)
            p_id = (self.node_id - 2**(i-1) + self.max_nodes) % self.max_nodes
            print(f"Checking if node {p_id} should have us in their {i}th finger table entry")
                
            # Find predecessor of p
            pred_info = self.find_predecessor(p_id)
            if pred_info.node_id == -1 or not pred_info.node_addr:
                continue
                    
            # Update that node's finger table
            pred = eval(pred_info.node_addr)
            print(f"Contacting node at {pred} to update finger table")
            
            pred_client, pred_transport = self.connect_to_node(*self.unpack_add(pred))
            if pred_client and pred_transport:
                try:
                    # Call fix_fingers() on the predecessor node
                    pred_client.fix_fingers()
                    print(f"Updated finger table for node at {pred}")
                except Exception as e:
                    print(f"Error updating finger table for node at {pred}: {e}")
                finally:
                    pred_transport.close()

    '''
    Hash fname to numerical key value 
    Key value: 0 - (MAX_NODES -1)
    '''
    def hash_filename(self, fname):
        # Sanitize
        if not fname:
            return None

        return hash(fname) % self.max_nodes
    
    '''
    Using the ID of their predecessor, nodes will accept keys with values 
    greater than their predecessor’s ID and less than or equal to their own ID
    '''
    def is_between(self, key, id1, id2):
         # Handle sanitization
        if key is None or key < 0 or id1 is None or id2 is None:
            return False
            
        # Special case: only one node in the network
        if id1 == id2:
            return True
            
        # Special case: if id1 and id2 are the same, but we have multiple nodes
        # This shouldn't happen in a correct Chord implementation
        if id1 == id2 and self.succ_id != self.node_id:
            print(f"Warning: is_between called with equal ids {id1} and {id2}")
            return False
            
        # Regular case (no wrap-around)
        if id1 < id2:
            return id1 < key <= id2
        # Wrap-around case
        else:  # id1 > id2
            return (id1 < key < self.max_nodes) or (0 <= key <= id2)
        
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
        n = int(ceil(log2(self.max_nodes))) 
        
        # Check finger table entries from highest to lowest
        for i in range(n, 0, -1):
            if i < len(self.finger_table) and self.finger_table[i] is not None:
                entry_id = self.finger_ids[i]
                # Check if this entry precedes target key but follows current node
                if self.is_between(entry_id, self.node_id, key):
                    return self.finger_table[i]
        
        # No suitable entry found, return own address
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
            return self.succ
        
        return closest_succ
        
    
    ''' 
    Train model when data reaches node;
    Stores trained weights, V and W, and status for client retrieval
    '''
    def train(self, fname):
            model = mlp()

            # Initialize model before training
            initialized_model = model.init_training_random(fname, _k=26, _h=20)
            if (initialized_model == False):
                raise Exception(f"Model initialization failed with file {fname}")

            # Train
            print(f"Training {fname}....")
            # Store local model 
            self.models[fname] = {
                'V': [],
                'W': [],
                'status': 'wait'
            }
            training_error_rate = model.train(eta = 0.0001, epochs = 250)
            if (training_error_rate == -1):
                self.work.remove(fname)
                raise Exception("Model training failed!")
            
           
            print(f"Finished training {fname} with error rate: {training_error_rate}")

            # New weights
            weights = model.get_weights()
            if not weights or len(weights) != 2:
                raise Exception(f"Failed to get weights for {fname}: got {weights}")
                
            trained_V, trained_W = weights

            # Store local model 
            self.models[fname] = {
                'V': trained_V,
                'W': trained_W,
                'status': 'ready'
            }
            
            # Remove file from work set 
            self.work.remove(fname)


    '''
    Returns a model from a node from an input dataset (filename)
    '''
    def get_model(self, fname):
        # Filename hashed to key value
        key = self.hash_filename(fname)

        # Checks if current node is responsible for file
        if self.reach_destination(key):
            if fname in self.models:
                model = self.models[fname]

                if model['status'] == 'ready':
                    # Convert numpy arrays to list
                    V = model['V'].tolist()
                    W = model['W'].tolist()

                    return WeightMatrices(V=V, W=W, status = 'ready')
                else:
                    return WeightMatrices(V=[], W=[], status = 'wait')
                
            else:
                return WeightMatrices(V=[], W=[], status = 'not found')
            
        # Not responsible for file, forward to another node
        else:
            node = self.forward_data(key)

            host, port = self.unpack_add(node)

            client, transport = self.connect_to_node(host, port)
            if client and transport:
                try:
                   return client.get_model(fname) 
                # Ensures that connection would be closed
                finally: 
                    transport.close() 
            else:
                print(f"Failed to connect to forwarding node {host}:{port}")
                return WeightMatrices(V=[], W=[], status='error: connection failed')
    '''
    Connect to another node in the network
    '''
    def connect_to_node(self, host, port):
        try:
            # Check if trying to connect to self
            if host == self.host and port == self.port:
                return None, None

            transport = TSocket.TSocket(host=host, port=port)
            transport = TTransport.TBufferedTransport(transport)
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            client = compute.Client(protocol)
            
            # Try to open the connection
            transport.open()
            print(f"Successfully connected to {host}:{port}")
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
            print("Error: Received None address in unpack_add")
            return None, None

        try:
            # Handle both string and tuple formats
            if isinstance(add, str):
                # Try to evaluate the string representation
                add_tuple = eval(add)
                host, port = add_tuple
                return host, port
            elif isinstance(add, tuple) and len(add) == 2:
                host, port = add
                return host, port
            else:
                raise ValueError(f"Invalid address format: {add}")
        except Exception as e:
            print(f"Error unpacking address {add}: {e}")
            return None, None

    '''
    Place input ML data (filename) into the network;
    Recursively finds the destination node
    '''
    def put_data(self, fname):

        # Record the data path
        if fname not in self.data_path:
            self.data_path[fname] = []
        self.data_path[fname].append(self.node_id)

        print(f"\n=== ROUTING DATA: {fname} ===")
        print(f"Current node: {self.node_id}")
        print(f"Current data path: {self.data_path[fname]}")

        # Hash fname to numerical key value (0 - MAX_NODES -1)
        key = self.hash_filename(fname)
        print(f"Hashed key: {key}")
        
        # Reach destination node
        if self.reach_destination(key):
            print(f"\n=== DESTINATION REACHED FOR: {fname} ===")
            print(f"Node {self.node_id} storing and training on file: {fname}")
            print(f"Responsible node: {self.node_id}")
            print(f"Complete path: {self.data_path[fname]}")
            print(f"Key range: {self.get_responsible_key_range()}")
            print(self.print_info())
            
            # Add to work set
            self.work.add(fname)
            # Start training
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

    '''
    Get responsible key range for node 
    '''
    def get_responsible_key_range(self):
        if self.pred_id is None:
            return f"[0-{self.max_nodes-1}]"
            
        # Keys from (predecessor, self]
        if self.pred_id < self.node_id:
            return f"({self.pred_id}-{self.node_id}]"
        else:  # Wrap 
            return f"({self.pred_id}-{self.max_nodes-1}] and [0-{self.node_id}]"
            
    def print_info(self):
        """Print information about the node state"""
        info = f"Node {self.node_id} Info:\n"
        info += f"Address: {self.addr}\n"
        info += f"Predecessor: {self.pred_id} at {self.pred}\n"
        info += f"Successor: {self.succ_id} at {self.succ}\n"
        
        info += "Finger Table:\n"
        for i in range(1, len(self.finger_table)):  # Start from 1, not 0
            if self.finger_table[i]:
                info += f"  [{i}]: Node {self.finger_ids[i]} at {self.finger_table[i]}\n"
        
        info += f"Responsible for keys: {self.get_responsible_key_range()}\n"
        
        info += "Stored Files:\n"
        for filename, model in self.models.items():
            info += f"  {filename}: {model['status']}\n"
        
        info += "Training Files:\n"
        for filename in self.work:
            info += f"  {filename}\n"
        
        info += "Data Paths:\n"
        for filename, path in self.data_path.items():
            info += f"  {filename}: {path}\n"
        
        return info

  
if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: python3 compute_node.py <host> <port> <supernode_host> <supernode_port>")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    supernode_host = sys.argv[3]
    supernode_port = int(sys.argv[4])
    
    # Create handler
    handler = ComputeNodeHandler(host, port, supernode_host=supernode_host, supernode_port=supernode_port)
    
    # Initialize node by joining the network
    handler.node_join()
    print("\n=== INITIAL NODE STATE ===")
    print(handler.print_info())

    # Start server
    processor = compute.Processor(handler)
    transport = TSocket.TServerSocket(host='0.0.0.0', port=port)
    tfactory = TTransport.TBufferedTransportFactory()
    pfactory = TBinaryProtocol.TBinaryProtocolFactory()
    
    # Create a threaded server
    server = TServer.TThreadedServer(processor, transport, tfactory, pfactory)

    # Print node info every 30 seconds in a separate thread
    def print_periodic_info():
        while True:
            time.sleep(30)
            print("\n=== PERIODIC NODE STATUS UPDATE ===")
            print(handler.print_info())
    
    print(f"Starting compute node {handler.node_id} on port {port}...")

    try:
        server.serve()
    except KeyboardInterrupt:
        print("Node shutting down")
    

    