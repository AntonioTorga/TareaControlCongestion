class CongestionControl:
    def __init__(self, MSS:int):
        self.current_state = "slow_start"
        self.MSS = MSS
        self.cwnd = MSS
        self.ssthresh = None
        self.DEBUG = False
    
    def get_cwnd(self):
        return self.cwnd
    
    def get_MSS_in_cwnd(self):
        return self.cwnd//self.MSS
    
    def event_ack_received(self):
        if self.current_state == "slow_start":
            self.cwnd += self.MSS
            if self.DEBUG: print("Ack received... Window size: ", self.get_MSS_in_cwnd)
        elif self.current_state == "congestion_avoidance":
            self.cwnd += self.MSS/self.get_MSS_in_cwnd()
            if self.DEBUG: print("Ack received... Window size: ", self.get_MSS_in_cwnd)
        if self.ssthresh!=None and self.cwnd >= self.ssthresh:
            self.current_state = "congestion_avoidance"
            if self.DEBUG: print("Changed to Congestion avoidance... Window size: ", self.get_MSS_in_cwnd)
    
    def event_timeout(self):
        if self.current_state == "slow_start":
            self.ssthresh = self.cwnd//2
            self.cwnd = self.MSS
            if self.DEBUG: print("Timeout... Window size: ", self.get_MSS_in_cwnd)

        
        elif self.current_state == "congestion_avoidance":
            self.current_state = "slow_start"
            self.ssthresh = self.cwnd//2
            self.cwnd = self.MSS
            if self.DEBUG: print("Changed to Slow Start...\nTimeout... Window size: ", self.get_MSS_in_cwnd)

    
    def is_state_slow_start(self):
        return self.current_state == "slow_start"
    
    def is_state_congestion_avoidance(self):
        return self.current_state == "congestion_avoidance"
    
    def get_ssthresh(self):
        return self.ssthresh