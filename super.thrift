service SupernodeService {
    # Returns an ID to use when joining the network 
    i32 request_join(1: i32 port) 
    
    # Confirm a new node's status in the network 
    void confirm_join(1: i32 node_id) 
    
    # Returns a random connection point (node) to join the network 
    string get_node() 
    
    # Debugging
    string print_info()
}