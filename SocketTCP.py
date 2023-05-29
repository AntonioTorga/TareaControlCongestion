import socket
from random import randint
import math
import slidingWindow as sw
import timerList as tm

timer = 1
head_size = 20
len_size = 16

class SocketTCP:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.direccion_destino = None
        self.direccion_origen = None
        self.secuencia = None
        self.prev_seq = None
        self.message_length = 0
        self.window = None
        self.window_size = 0
        self.timer_list = None
        self.initial_seq = 0
        self.timeout = 0
        self.window = None
        self.acknowledged = []
        self.receiving = []
        self.received = []

    def bind(self,address):
        self.socket.bind(address)
        self.direccion_origen = address
    
    def connect(self,address):
        self.socket.settimeout(timer)
        self.secuencia = randint(0,100)
        first_message = create_tcp_msg(SYN=1,SEQ=self.secuencia)
        acknowledge = False
        while(not acknowledge):
            try:
                #First way: Sending SYN, SEQ = X
                self.socket.sendto(first_message.encode(),address)
                #Second way: Expecting SYN+ACK, SEQ = X+1
                second_message, ns_adress = self.socket.recvfrom(head_size)
                second_message = self.parse_segment(second_message.decode())
                if second_message["SYN"]==1 and second_message["ACK"]==1 and second_message["SEQ"]==self.secuencia+1:
                    self.secuencia += 2
                    acknowledge = True
            except TimeoutError:
                print("Timeout waiting for FIN+ACK... Retrying")
        #Third way: Sending ACK, SEQ = X+2, Mandando a nuevo socket
        third_message = create_tcp_msg(ACK=1,SEQ = self.secuencia) 
        self.socket.sendto(third_message.encode(),address)
        self.direccion_destino = (ns_adress[0], ns_adress[1])

    def accept(self):
        # First way: SYN, SEQ = X
        first_message, address = self.socket.recvfrom(head_size)
        first_message = self.parse_segment(first_message.decode())
        if first_message["SYN"] == 1: #check more?
            acknowledge = False
            self.secuencia = first_message["SEQ"]
            second_message = create_tcp_msg(SYN=1,ACK=1,SEQ=self.secuencia+1)
            while(not acknowledge):
                # Second way: SYN+ACK, SEQ = X+1
                new_socket = SocketTCP()
                new_socket.bind((self.direccion_origen[0], self.direccion_origen[1]+self.secuencia))
                new_socket.secuencia = self.secuencia + 2
                new_socket.direccion_destino = address
                new_socket.socket.sendto(second_message.encode(),address)
                # Third way: ACK, SEQ = X+2
                third_message, address = self.socket.recvfrom(head_size)
                third_message = self.parse_segment(third_message.decode())
                if third_message["ACK"] and third_message["SEQ"] == self.secuencia+2: # Si es ACK perfecto
                    acknowledge = True
                    return new_socket, new_socket.direccion_origen
                elif third_message["SYN"] and third_message["SEQ"] == self.secuencia: # Se perdio SYN+ACK
                    pass
    
    def send_using_stop_and_wait(self, message):
        # Send message length
        self.socket.settimeout(timer)
        message = message.decode()
        length = len(message)
        len_received = False
        while(not len_received):
            try:
                self.socket.sendto(create_tcp_msg(msg=str(length), SEQ=self.secuencia).encode(),self.direccion_destino)
                msg, add = self.socket.recvfrom(head_size + len_size)
                msg = self.parse_segment(msg.decode())
                if msg["ACK"] == 1 and msg["SEQ"] == self.secuencia + 1:
                    try:
                        buff_size = int(msg["DATOS"])
                        len_received = True
                        self.secuencia += 1
                    except:
                        self.socket.sendto(create_tcp_msg(ACK=1, SEQ=msg["ACK"]).encode(),self.direccion_destino)
                        print(self.create_segment(msg))
            except TimeoutError:
                print("Timeout sending size of string... Retrying")
        # Send message
        iterations = math.ceil(length/buff_size)
        i = 0
        while i < iterations:
            tosend = message[i*buff_size:(i+1)*buff_size]
            print(f"Sending message part {i+1}/{iterations} \n Content: {tosend}")
            received = False
            tcp_message = create_tcp_msg(msg=tosend,SEQ=self.secuencia).encode()
            expected_seq = self.secuencia + len(tcp_message)
            while(not received):
                try:
                    self.socket.sendto(tcp_message,self.direccion_destino)
                    msg,add = self.socket.recvfrom(head_size)
                    msg = self.parse_segment(msg.decode())
                    if msg["ACK"]==1 and msg["SEQ"]==expected_seq:
                        received = True
                        self.secuencia = expected_seq
                        i += 1
                except TimeoutError:
                    print(f"Timeout sending message part {i+1}/{iterations}... Retrying \n SEQ = {self.secuencia}, expecting ack SEQ = {expected_seq}" )
    
    def recv_using_stop_and_wait(self, buffer_size):
        while self.message_length == 0:
            # Recibimos largo del mensaje
            len_msg,add = self.socket.recvfrom(head_size + buffer_size)
            len_len_msg = len(len_msg)
            len_msg = self.parse_segment(len_msg.decode())
            try:
                self.message_length = int(len_msg["DATOS"])
            except ValueError:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=len_msg["SEQ"]).encode(),self.direccion_destino)
            self.prev_seq = len_msg["SEQ"]
            self.secuencia = len_msg["SEQ"] + 1
            self.socket.sendto(create_tcp_msg(msg= str(buffer_size), ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)
        
        # Recibiendo mensajes
        received_msg = False
        while(not received_msg):
            msg, add = self.socket.recvfrom(head_size + buffer_size)
            expected_seq = self.secuencia + len(msg)
            msg = self.parse_segment(msg.decode())
            print(f"Waiting for SEQ = {self.secuencia}, accepting PREV_SEQ = {self.prev_seq} \n Arrived SEQ = {msg['SEQ']}")
            if msg["SEQ"] == self.secuencia:
                self.prev_seq = self.secuencia
                self.secuencia = expected_seq
                self.message_length -= len(msg["DATOS"])
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)
                received_msg = True
                return msg["DATOS"].encode()
            elif msg["SEQ"] == self.secuencia - 1:
                self.socket.sendto(create_tcp_msg(msg = str(buffer_size),ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)
            elif msg["SEQ"] == self.prev_seq:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)

    def send_using_selective_repeat(self, message):
        message = message.decode()
        self.window_size = 3
        self.acknowledged = [False] * self.window_size * 2
        buff_size = 16
        self.initial_seq = self.secuencia
        segments = math.ceil(len(message)/buff_size)
        self.timeout = 1
        # Creamos data list
        data_list = [len(message)]
        for i in range(0,segments):
            data_list.append(message[i*buff_size:(i+1)*buff_size])
        # Creamos ventana y timer list, timer list es de tamaño 2*window_size para poder referenciar más fácil los timers.
        self.window = sw.SlidingWindow(self.window_size, data_list, self.initial_seq)
        self.timer_list = tm.TimerList(self.timeout, self.window_size*2)
        self.socket.setblocking(False)
        # Enviamos los primeros mensajes.
        for wnd_index in range(self.window_size):
            current_data = self.window.get_data(wnd_index)
            if current_data is None:
                break
            current_seq = self.window.get_sequence_number(wnd_index)
            self.receiving.append(current_seq)
            current_segment = create_tcp_msg(msg=current_data, SEQ=current_seq).encode()
            self.socket.sendto(current_segment, self.direccion_destino)
            self.timer_list.start_timer(current_seq - self.initial_seq)
        

        while True:
            try: 
                timeouts = self.timer_list.get_timeouts()
                if len(timeouts) > 0:
                    for timeout in timeouts:
                        wnd_index = self.get_window_index(self.initial_seq + timeout)
                        current_data = self.window.get_data(wnd_index)
                        current_seq = self.window.get_sequence_number(wnd_index)
                        current_segment = create_tcp_msg(msg=current_data, SEQ=current_seq).encode()
                        self.socket.sendto(current_segment, self.direccion_destino)
                        self.timer_list.start_timer(timeout)
                
                msg, add = self.socket.recvfrom(head_size+buff_size)
            except BlockingIOError:
                continue

            msg = self.parse_segment(msg.decode())

            if msg["ACK"] == 1 and msg["SEQ"] in self.receiving:
                self.ack(msg["SEQ"])
                self.window_move()
            
            if self.window.get_data(0) is None:
                break

    def recv_using_selective_repeat(self, buffer_size):
        self.window_size = 3
        self.window = sw.SlidingWindow(self.window_size, [], 0)
        self.socket.setblocking(False)
        self.initial_seq = self.secuencia
        self.receiving = [self.initial_seq + i for i in range(self.window_size)]
        #receive len
        received_len = False
        while not received_len:
            try:
                len_msg,add = self.socket.recvfrom(head_size + buffer_size)
                len_msg = self.parse_segment(len_msg.decode())
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=len_msg["SEQ"]).encode(),self.direccion_destino)
                self.message_length = int(len_msg["DATOS"])
                received_len = True
            except ValueError:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)

        self.received = [False] * math.ceil(self.message_length/buffer_size)
        while True:
            msg,address = self.socket.recvfrom(head_size + buffer_size)
            msg = self.parse_segment(msg.decode())
            if msg["SEQ"] in self.receiving:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=msg["SEQ"]).encode(),self.direccion_destino)
                self.save_data(msg["DATOS"],msg["SEQ"])
                self.window.put_data(msg["DATOS"],msg["SEQ"], self.get_window_index(msg["SEQ"]))
                self.window_move_recv()
                return msg["DATOS"].encode()
            else:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=msg["SEQ"]).encode(),self.direccion_destino)
    
    def send(self,message, mode = "stop_and_wait"):
        if mode == "stop_and_wait":
            self.send_using_stop_and_wait(message)
        if mode == "selective_repeat":
            self.send_using_selective_repeat(message)

    def recv(self,buffer_size, mode = "stop_and_wait"):
        if mode == "stop_and_wait":
            return self.recv_using_stop_and_wait(buffer_size)
        if mode == "selective_repeat":
            return self.recv_using_selective_repeat(buffer_size)

    def close(self):
        self.socket.settimeout(timer)
        # Send FIN
        fin_sent = False
        timeouts = 3
        while(not fin_sent and timeouts > 0):
            try:
                self.socket.sendto(create_tcp_msg(FIN=1,SEQ=self.secuencia).encode(),self.direccion_destino)
                msg,add = self.socket.recvfrom(head_size)
                msg = self.parse_segment(msg.decode())
                if msg["FIN"] == 1 and msg["ACK"] == 1 and msg["SEQ"] == self.secuencia + 1:
                    fin_sent = True
                    self.secuencia += 1
            except TimeoutError:
                timeouts -= 1
                print("Timeout receiving FIN+ACK... Retrying")
        if timeouts == 0:
            print("Timeout limit reached, closing connection")
            self.direccion_destino = None
            self.secuencia = None
            self.prev_seq = None
            return 
        # Send ACK
        timeouts = 3
        while(timeouts > 0):
            try:
                self.socket.sendto(create_tcp_msg(ACK=1,SEQ=self.secuencia + 1).encode(),self.direccion_destino)
                msg,add = self.socket.recvfrom(head_size) #just waiting
            except TimeoutError:
                timeouts -= 1
        self.direccion_destino = None
        self.secuencia = None
        self.prev_seq = None
        return
    
    def recv_close(self):
        #receive FIN
        fin_received = False
        while not fin_received:
            fin, add = self.socket.recvfrom(head_size)
            fin = self.parse_segment(fin.decode())
            if fin["FIN"] == 1 and fin["SEQ"] == self.secuencia:
                fin_received = True
                self.secuencia += 1
        self.socket.settimeout(timer)
        # Send ACK
        timeouts = 3
        ack_received = False
        while(timeouts > 0 and not ack_received): 
            self.socket.sendto(create_tcp_msg(FIN=1,ACK=1,SEQ=self.secuencia).encode(),self.direccion_destino)
            try:
                msg,add = self.socket.recvfrom(head_size) 
                msg = self.parse_segment(msg.decode())
                if msg["ACK"] == 1 and msg["SEQ"] == self.secuencia + 1:
                    ack_received = True
            except TimeoutError:
                timeouts -= 1
                print("Timeout receiving ACK... Retrying")
        if  timeouts==0:
            print("Timeout limit reached, closing connection")
        self.secuencia = None
        self.prev_seq = None
        self.direccion_destino = None

    def parse_segment(self, segment):
        parsed_seg = {}
        index = segment.find("|||")
        parsed_seg["SYN"] = int(segment[:index])
        segment = segment[index+3:]
        index = segment.find("|||")
        parsed_seg["ACK"] = int(segment[:index])
        segment = segment[index+3:]
        index = segment.find("|||")
        parsed_seg["FIN"] = int(segment[:index])
        segment = segment[index+3:]
        index = segment.find("|||")
        parsed_seg["SEQ"] = int(segment[:index])
        segment = segment[index+3:]
        parsed_seg["DATOS"] = segment
        
        return parsed_seg
    def create_segment(self, parsed_seg):
        segment = ""
        segment += str(parsed_seg["SYN"]) + "|||"
        segment += str(parsed_seg["ACK"]) + "|||"
        segment += str(parsed_seg["FIN"]) + "|||"
        segment += str(parsed_seg["SEQ"]) + "|||"
        segment += str(parsed_seg["DATOS"]) 

        return segment
    def get_window_index(self,seq):
        for i in range(self.window_size):
            if self.window.get_seq(i) == seq:
                return i
        return -1
    
    def ack(self,seq):
        self.acknowledged[seq - self.initial_seq] = True
        timer_index = seq - self.initial_seq
        self.timer_list.stop_timer(timer_index)
    def window_move(self):
        wnd_index = self.window_size - 1
        i = 0
        seq = self.window.get_seq(i)

        while self.acknowledged[seq - self.initial_seq]:
            self.window.move_window(1)
            self.receiving.remove(seq)
            self.acknowledged[seq-self.initial_seq] = False

            if not self.window.get_data(wnd_index) is None:
                current_data = self.window.get_data(wnd_index)
                current_seq = self.window.get_sequence_number(wnd_index)
                self.receiving.append(current_seq)
                current_segment = create_tcp_msg(current_data,SEQ=current_seq).encode()
                self.socket.sendto(current_segment,self.direccion_destino)
                timer_index = current_seq - self.initial_seq
                self.timer_list.start_timer(timer_index)

            i += 1
            seq = self.window.get_seq(i)
    def window_move_recv(self):
        # Cambiar los que recibimos
        wnd_index = self.window_size - 1
        while self.window.get_data(0) != None:
            self.receiving.remove(self.window.get_sequence_number(0))
            self.window.move_window(1)
            self.receiving.append(self.window.get_sequence_number(wnd_index))
        
    def save_data(self, data, seq):
        seq_reps = len(self.received)//(self.window_size * 2)
        i = 0
        while(i < seq_reps and self.received[(seq-self.initial_seq) + self.window_size* 2 *i] != False):
            i+=1
        if i >= seq_reps:
            return
        self.received[(seq-self.initial_seq) + self.window_size* 2 *i] = data
        
        
def create_tcp_msg(msg="", SYN=0, ACK=0, FIN=0, SEQ=0):
    segment = ""
    segment += str(SYN) + "|||"
    segment += str(ACK) + "|||"
    segment += str(FIN) + "|||"
    segment += str(SEQ) + "|||"
    segment += str(msg) 
    return segment
