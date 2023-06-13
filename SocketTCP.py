import socket
import random
import timerList as tm
import slidingWindowCC as swcc
from random import randint
import CongestionControl as cc
import math


class SocketTCP:
    def __init__(self):
        """Este constructor contiene solo algunas de las cosas que puede necesitar para que funcione su código. Puede agregar tanto como ud. necesite."""
        self.socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.buff_size_udp = 500
        self.origin_address = tuple()
        self.destiny_address = tuple()
        self.timeout = 1  # seconds
        self.socket_udp.settimeout(self.timeout)
        self.window_size = 3
        self.seq = None
        self.initial_seq = None
        self.segment_count = 0
        self.loss_probability = 0
        self.DEBUG = False
        self.expected_syn_ack_seq_number = None
        self.last_ack_from_handshake = None
        self.bytes_to_receive = None
        self.message_reminder = b''
        self.prev_seq = None
        self.congestion_controler = cc.CongestionControl(8)
        self.congestion_controler.DEBUG = self.DEBUG

    def bind(self,address):
        self.socket_udp.bind(address)
        self.origin_address = address
    
    def connect(self,address):
        self.socket_udp.settimeout(self.timeout)
        self.seq = randint(0,100)
        first_message = create_tcp_msg(SYN=1,SEQ=self.seq)
        acknowledge = False
        while(not acknowledge):
            try:
                #First way: Sending SYN, SEQ = X
                self.socket_udp.sendto(first_message.encode(),address)
                #Second way: Expecting SYN+ACK, SEQ = X+1
                second_message, ns_adress = self.socket_udp.recvfrom(self.buff_size_udp)
                second_message = self.parse_segment(second_message.decode())
                if second_message["SYN"]==1 and second_message["ACK"]==1 and second_message["SEQ"]==self.seq+1:
                    self.seq += 2
                    acknowledge = True
            except TimeoutError:
                print("Timeout waiting for FIN+ACK... Retrying")
        #Third way: Sending ACK, SEQ = X+2, Mandando a nuevo socket_udp
        third_message = create_tcp_msg(ACK=1,SEQ = self.seq) 
        self.save_last_ack_from_handshake()
        self.socket_udp.sendto(third_message.encode(),address)
        self.destiny_address = (ns_adress[0], ns_adress[1])
        
    def accept(self):
        # First way: SYN, SEQ = X
        first_message, address = self.socket_udp.recvfrom(self.buff_size_udp)
        first_message = self.parse_segment(first_message.decode())
        if first_message["SYN"] == 1: #check more?
            acknowledge = False
            self.seq = first_message["SEQ"]
            second_message = create_tcp_msg(SYN=1,ACK=1,SEQ=self.seq+1)
            while(not acknowledge):
                # Second way: SYN+ACK, SEQ = X+1
                new_socket = SocketTCP()
                new_socket.bind((self.origin_address[0], self.origin_address[1]+self.seq))
                new_socket.seq = self.seq + 2
                new_socket.destiny_address = address
                new_socket.socket_udp.sendto(second_message.encode(),address)
                # Third way: ACK, SEQ = X+2
                third_message, address = self.socket_udp.recvfrom(self.buff_size_udp)
                third_message = self.parse_segment(third_message.decode())
                if third_message["ACK"] and third_message["SEQ"] == self.seq+2: # Si es ACK perfecto
                    acknowledge = True
                    return new_socket, new_socket.origin_address
                elif third_message["SYN"] and third_message["SEQ"] == self.seq: # Se perdio SYN+ACK
                    pass

    def close(self):
            self.socket_udp.settimeout(self.timeout)
            # Send FIN
            fin_sent = False
            timeouts = 3
            while(not fin_sent and timeouts > 0):
                try:
                    self.socket_udp.sendto(create_tcp_msg(FIN=1,SEQ=self.seq).encode(),self.destiny_address)
                    msg,add = self.socket_udp.recvfrom(self.buff_size_udp) 
                    msg = self.parse_segment(msg.decode())
                    if msg["FIN"] == 1 and msg["ACK"] == 1 and msg["SEQ"] == self.seq + 1:
                        fin_sent = True
                        self.seq += 1
                except TimeoutError:
                    timeouts -= 1
                    print("Timeout receiving FIN+ACK... Retrying")
            if timeouts == 0:
                print("Timeout limit reached, closing connection")
                self.destiny_address = None
                self.seq = None
                self.prev_seq = None
                return 
            # Send ACK
            timeouts = 3
            while(timeouts > 0):
                try:
                    self.socket_udp.sendto(create_tcp_msg(ACK=1,SEQ=self.seq + 1).encode(),self.destiny_address)
                    msg,add = self.socket_udp.recvfrom(self.buff_size_udp) #just waiting
                except TimeoutError:
                    timeouts -= 1
            self.destiny_address = None
            self.seq = None
            self.prev_seq = None
            return

    def recv_close(self):
        #receive FIN
        fin_received = False
        while not fin_received:
            fin, add = self.socket_udp.recvfrom(self.buff_size_udp)
            fin = self.parse_segment(fin.decode())
            if fin["FIN"] == 1 and fin["SEQ"] == self.seq:
                fin_received = True
                self.seq += 1
        self.socket_udp.settimeout(self.timeout)
        # Send ACK
        timeouts = 3
        ack_received = False
        while(timeouts > 0 and not ack_received): 
            self.socket_udp.sendto(create_tcp_msg(FIN=1,ACK=1,SEQ=self.seq).encode(),self.direccion_destino)
            try:
                msg,add = self.socket_udp.recvfrom(self.buff_size_udp) 
                msg = self.parse_segment(msg.decode())
                if msg["ACK"] == 1 and msg["SEQ"] == self.seq + 1:
                    ack_received = True
            except TimeoutError:
                timeouts -= 1
                print("Timeout receiving ACK... Retrying")
        if  timeouts==0:
            print("Timeout limit reached, closing connection")
        self.seq = None
        self.prev_seq = None
        self.direccion_destino = None

    def send(self, message,mode="go_back_n"):
        if mode == "go_back_n":
            self.send_using_go_back_n(message)
    
    def recv(self,buffer_size,mode="go_back_n"):
        if mode == "go_back_n":
            return self.recv_using_go_back_n(buffer_size)
        
    def send_using_go_back_n(self, message: bytes):
        # dividimos el mensaje en trozos de 16 bytes
        message_length = (str(len(message))).encode()
        max_data_size_per_segment = self.congestion_controler.MSS
        # dejamos el primer elemento de data_list como el message_length (bytes de un string con el numero)
        data_list = [message_length] + self.create_message_slices(message, max_data_size_per_segment)

        # creamos una ventana con el data_list 
        initial_seq = self.get_last_seq_from_handshake()
        sender_window = swcc.SlidingWindowCC(self.congestion_controler.get_MSS_in_cwnd, data_list, initial_seq)

        # creamos un timer usando TimerList, en go back N tenemos 1 unico timer por ventana
        # asi que hacemos que nuestro timer_list sea de tamaño 1 y usamos el timeout del constructor de SocketTCP
        timer_list = tm.TimerList(self.timeout, 1)
        t_index = 0

        # enviamos la ventana inicial
        for wnd_index in range(self.window_size):
            # partimos armando y enviando el primer segmento
            current_data = sender_window.get_data(wnd_index)
            # si current_data == None, no quedan cosas en la ventana y salimos del for
            if current_data is None:
                break
            current_seq = sender_window.get_sequence_number(wnd_index)

            current_segment = self.create_data_segment(current_seq, current_data)
            self.send_con_perdidas(current_segment, self.destiny_address)

            if wnd_index == 0:
                # despues de enviar el primer elemento de la ventana corre el timer
                timer_list.start_timer(t_index)
            else:
                self.update_seq_number(1)

        # para poder usar este timer vamos poner nuestro socket como no bloqueante
        self.socket_udp.setblocking(False)

        # y para manejar esto vamos a necesitar un while True
        while True:
            try:
                # en cada iteración vemos si nuestro timer hizo timeout
                timeouts = timer_list.get_timed_out_timers()

                # si hizo timeout reenviamos toda la ventana
                if len(timeouts) > 0:
                    timer_list.stop_timer(t_index)
                    for i in range(self.window_size):
                        # partimos armando y enviando el primer segmento
                        wnd_index = i
                        current_data = sender_window.get_data(wnd_index)
                        if current_data is None:
                            timer_list.start_timer(t_index)
                            break
                        current_seq = sender_window.get_sequence_number(wnd_index)
                        self.seq = current_seq
                        current_segment = self.create_data_segment(current_seq, current_data)
                        self.send_con_perdidas(current_segment, self.destiny_address)
                        if wnd_index == 0:
                            # despues de enviar el primer elemento de la ventana corre el timer
                            timer_list.start_timer(t_index)
                    self.congestion_controler.event_timeout()
                    self.window_size = self.congestion_controler.get_MSS_in_cwnd()
                    sender_window.update_window_size(self.window_size)
                    

                # si no hubo timeout esperamos el ack del receptor
                answer, address = self.socket_udp.recvfrom(self.buff_size_udp)

            except BlockingIOError:
                # como nuestro socket no es bloqueante, si no llega nada entramos aquí y continuamos (hacemos esto en vez de usar threads)
                continue

            else:
                # si no entramos al except (y no hubo otro error) significa que llegó algo!
                # si lo que llegó es el syn_ack del accept (es decir se perdió el último ack del handshake) reenviamos ese ack y NO DETENEMOS EL TIMER
                # queremos que llegue al timeout y se reenvie la ventan
                if self.check_syn_ack(answer, self.expected_syn_ack_seq_number()):
                    # reenviamos el ultimo ack del handshake
                    self.send_con_perdidas(self.last_ack_from_handshake(), self.destiny_address)

                # si la respuesta es un ack válido
                if self.is_valid_ack_go_back_n(sender_window, answer):
                    # detenemos el timer
                    timer_list.stop_timer(t_index)
                    # calculamos cuanto se debe mover la ventana
                    steps_to_move = self.steps_to_move_go_back_n(sender_window, answer)
                    # movemos la ventana de a 1 paso mientras enviamos los segmentos correspondientes
                    wnd_index = self.window_size - 1

                    for k in range(1, steps_to_move + 1):
                        sender_window.move_window(1)
                        current_data = sender_window.get_data(wnd_index)
                        # si hay algo por mandar, lo mando
                        if current_data is not None:
                            current_seq = sender_window.get_sequence_number(wnd_index)
                            self.seq = current_seq
                            current_segment = self.create_data_segment(current_seq, current_data)
                            self.send_con_perdidas(current_segment, self.destiny_address)
                            # si es el primer elemento de la ventana, inicio el timer
                            if k == 1:
                                timer_list.start_timer(t_index)
                            # si no, me preocupo de mantener consistente el numero de secuencia que recuerda el socket
                            else:
                                self.update_seq_number(len(current_data))
                        else:
                            timer_list.start_timer(t_index)
                    self.congestion_controler.event_ack_received()
                    self.window_size = self.congestion_controler.get_MSS_in_cwnd()
                    sender_window.update_window_size(self.window_size)


                    # si luego de avanzar en la ventana, el primer elemento es None, significa que recibimos un ACK para cada elemento
                    if sender_window.get_data(0) is None:
                        # y retornamos (ya recibimos todos los ACKs)
                        return

    def recv_using_go_back_n(self, buff_size: int) -> bytes:
        # si tenia un timeout activo en el objeto, lo desactivo
        self.socket_udp.settimeout(None)

        expected_seq = self.seq

        # inicializamos el mensaje total. La función start_current_message retorna b'' si espero un nuevo mensaje
        # y puede partir con algo diferente si me quedo una trozo de mensaje guardado desde una llamada de recv anterior
        full_message = self.get_message_reminder()

        # si el mensaje es nuevo (no estamos a la mitad de recibir un mensaje), esperamos el message_length
        if self.expecting_new_message():
            # esperamos el largo del mensaje
            while True:
                first_message_slice, address = self.socket_udp.recvfrom(self.buff_size_udp)
                # si es el numero de secuencia que esperaba, extraigo el largo del mensaje
                if self.check_seq(first_message_slice, expected_seq) and not self.check_ack(first_message_slice, expected_seq):
                    # la funcion get_message_length_from_segment retorna el message_length en int
                    message_length = self.get_message_length_from_segment(first_message_slice)

                    # le indicamos al socket cuantos bytes debera recibir
                    self.set_bytes_to_receive(message_length)

                    # respondemos con el ack correspondiente
                    current_ack = self.create_ack(expected_seq)
                    self.send_con_perdidas(current_ack, self.destiny_address)

                    # recordamos lo ultimo que mandamos
                    self.last_segment_sent = current_ack

                    # actualizamos el SEQ esperado
                    self.update_seq_number(1)

                    # salimos del loop
                    break
                # si el número de secuencia no es lo que esperaba, reenvio el ultimo segmento
                else:
                    # reenviamos lo ultimo que mandamos
                    self.send_con_perdidas(self.last_segment_sent, self.destiny_address)

        # reviso si recibi el mensaje completo, pero no lo pude retornar antes y tengo un trozo guardado
        if self.can_return_reminder_message():
            # cortamos el mensaje para que su tamaño maximo sea buff_size
            message_to_return = full_message[0:buff_size]
            message_reminder = full_message[buff_size:len(full_message)]

            # si sobra un trozo de mensaje lo guardamos
            self.save_message_reminder(message_reminder)
            return message_to_return

        # despues de recibir el message_length se continua con la recepcion
        while True:
            expected_seq = self.seq
            message_slice, address = self.socket_udp.recvfrom(self.buff_size_udp)

            # si es el numero de secuencia que esperaba, extraigo los datos
            if self.check_seq(message_slice, expected_seq):
                message_slice_data = self.get_data_from_segment(message_slice)
                full_message += message_slice_data
                # actualizamos la cantidad de bytes que nos queda por recibir
                self.update_bytes_to_receive(len(message_slice_data))

                # respondemos con el ack correspondiente
                expected_seq += self.get_message_length_from_segment(message_slice)
                current_ack = self.create_ack(expected_seq)

                self.send_con_perdidas(current_ack, self.destiny_address)

                # recordamos lo ultimo que mandamos
                self.last_segment_sent = current_ack

                # actualizamos el SEQ esperado
                self.update_seq_number(self.get_message_length_from_segment(message_slice))

                # verificamos si hay que retornar
                if len(full_message) >= buff_size or self.get_bytes_to_receive() == 0:
                    # cortamos el mensaje para que su tamaño maximo sea buff_size
                    message_to_return = full_message[0:buff_size]
                    message_reminder = full_message[buff_size:len(full_message)]

                    # si sobra un trozo de mensaje lo guardamos
                    self.save_message_reminder(message_reminder)
                    return message_to_return
            else:
                # reenviamos lo ultimo que mandamos
                self.send_con_perdidas(self.last_segment_sent, self.destiny_address)

    @staticmethod
    def parse_segment(segment: bytes):
        """Funcion que parsea un segmento a una estructura de datos y retorna dicha estructura. Esta funcion debe ser implementada por ud."""
        parsed_seg = {}
        segment = segment.decode()
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

    @staticmethod
    def create_segment(data_structure) -> bytes:
        """Funcion crea un segmento a partir de una estructura de datos definida (la misma que retorna parse_segment). Esta funcion debe ser implementada por ud."""
        segment = ""
        segment += str(data_structure["SYN"]) + "|||"
        segment += str(data_structure["ACK"]) + "|||"
        segment += str(data_structure["FIN"]) + "|||"
        segment += str(data_structure["SEQ"]) + "|||"
        segment += str(data_structure["DATOS"]) 
        return segment.encode()

    def set_loss_probability(self, loss_probability: int):
        """Cambia el parametro loss_probability dentro del objeto. Este parametro se utiliza para probar perdidas de forma manual (sin usar netem)."""
        self.loss_probability = loss_probability

    def set_debug_on(self):
        self.DEBUG = True

    def set_debug_off(self):
        self.DEBUG = False

    def send_con_perdidas(self, segment: bytes, address: (str, int)):
        """Funcion que fuerza perdidas al llamar a send. Si no desea utilizarla puede poner su tasa de perdida en 0 llamando a set_loss_probability"""
        # sacamos un número entre 0 y 100 de forma aleatoria
        random_number = random.randint(0, 100)

        # si el random_number es mayor o igual a la probabilidad de perdida enviamos el mensaje
        if random_number >= self.loss_probability:
            self.socket_udp.sendto(segment, address)
            if self.DEBUG:
                print(f"Se envió: {segment}")
        else:
            if self.DEBUG:
                print(f"Oh no, se perdió: {segment}")

    def add_padding_to_data_list(self, data_list: list, SEQ: int) -> list:
        """Rellena la lista de datos con b'' para que el numero de secuencia inicial calce con SEQ."""
        i = 0
        n = self.window_size
        padding = []
        while i + self.initial_seq != SEQ:
            padding.append(b'')
            i += 1
        return padding + data_list

    @staticmethod
    def move_window_to_data_start(sliding_window: swcc.SlidingWindowCC) -> swcc.SlidingWindowCC:
        """Mueve una ventana hasta que comienzan los datos (es decir, se mueve hasta no ver el relleno de b'' o padding)"""
        while sliding_window.get_data(0) == b'':
            sliding_window.move_window(1)
        return sliding_window

    def save_expected_syn_ack_seq_number(self, SEQ: int):
        """Durante el handshake se debe guardar el numero de secuencia del SYN ACK esperado, de esta forma si al llamar a send se recibe dicho SYN ACK podremos verificar su correctitud. Esta
        funcion debe ser implementada por ud."""
        self.expected_syn_ack_seq_number = SEQ
        
    def expected_syn_ack_seq_number(self):
        """Retorna el numero de secuencia del SYN ACK esperado en el handshake, este numero fue guardado al llamar a save_expected_syn_ack_seq_number. Esta
        funcion debe ser implementada por ud."""
        return self.expected_syn_ack_seq_number

    def save_last_ack_from_handshake(self):
        """Durante el handshake se debe guardar el ultimo ACK enviado, de esta forma si al llamar a send se recibe dicho SYN ACK podremos reenviar dicho ACK. Esta funcion debe ser implementada
        por ud."""
        self.last_ack_from_handshake = self.create_ack(self.seq)

    def last_ack_from_handshake(self):
        """Retorna el ultimo segmento ACK del handshake. Este segmento fue guardado al llamar a save_last_ack_from_handshake. Esta funcion debe ser implementada por ud."""
        return self.last_ack_from_handshake

    def save_message_reminder(self, message: bytes):
        """Si al llamar recv es necesario retornar una cantidad de bytes menor que la que se ha recibido, entonces se guarda el sobrante para retornarlo en una siguiente llamada de recv.
        Esta funcion debe ser implementada por ud."""
        self.message_reminder = message
        
    def can_return_reminder_message(self) -> bool:
        """Verifica si es posible retornar solo utilizando el resto de mensaje guardado dentro del objeto SocketTCP, es decir, retorna True si ya se recibieron todos los bytes del mensaje desde el
        sender, pero quedaba un resto de bytes que no habia sido retornado previamente. Este resto fue previamente guardado usando la funcion save_message_reminder. Esta funcion debe ser
        implementada por ud."""
        return self.get_bytes_to_receive() == 0 and len(self.message_reminder) > 0

    def expecting_new_message(self) -> bool:
        """Determina si se esta esperando un nuevo mensaje en recv (es decir esperamos que el primer mensaje traiga el message_length). Esta funcion debe ser implementada por ud."""
        return self.get_bytes_to_receive() == 0

    def get_last_seq_from_handshake(self) -> int:
        """Retorna el ultimo numero de secuencia del handshake. Este numero es el mismo para el socket que llama a connect y el socket que llama a accept. Esta funcion debe ser implementada por ud."""
        last_ack = self.parse_segment(self.last_ack_from_handshake)
        return last_ack["SEQ"]

    def get_message_reminder(self) -> bytes:
        """Retorna el resto de mensaje guardado por la funcion save_message_reminder. Si no hay un resto guardado debe retornar b''. Esta funcion debe ser implementada por ud."""
        return self.message_reminder

    def get_data_from_segment(self, segment: bytes) -> bytes:
        """Extrae los datos desde un segmento en bytes. Esta funcion debe ser implementada por ud."""
        segment = self.parse_segment(segment)
        return segment["DATOS"].encode()
    
    def get_message_length_from_segment(self, segment: bytes) -> int:
        """Extrae el message_length desde el segmento en bytes. El message_length se retorna como int. Esta funcion debe ser implementada por ud."""
        return len(self.get_data_from_segment(segment))

    def get_bytes_to_receive(self) -> int:
        """Indica cuantos bytes quedan por recibir, este parametro debe almacenarse dentro del objeto SocketTCP. Esta funcion debe ser implementada por ud."""
        return self.bytes_to_receive

    def set_bytes_to_receive(self, message_length: int):
        """Guarda el message_length para saber cuantos bytes se deberan recibir. Esta funcion debe ser implementada por ud."""
        self.bytes_to_receive = message_length

    def update_bytes_to_receive(self, message_slice: int):
        """Actualiza la cantidad de datos que queda por recibir dado que llego message_slice. Esta funcion debe ser implementada por ud."""
        self.bytes_to_receive -= message_slice

    def create_message_slices(self, message: bytes, max_data_size_per_segment: int) -> list:
        """Dado un mensaje bytes message, crea una lista con trozos del mensaje de tamaño maximo max_data_size_per_segment. Cada elemento en la lista retornada es de tipo bytes. Esta funcion debe ser
        implementada por ud."""
        segments = math.ceil(len(message)/max_data_size_per_segment)
        data_list = []
        for i in range(0,segments):
            data_list.append(message[i*max_data_size_per_segment:(i+1)*max_data_size_per_segment])
        return data_list

    def create_syn(self, SEQ: int) -> bytes:
        """Crea un segmento SYN con numero de secuencia SEQ, usa la funcion create_segment y retorna bytes. Esta funcion debe ser implementada por ud."""
        return self.create_segment({"SYN":1,"ACK":0,"FIN":0,"SEQ":SEQ,"DATOS":""})

    def create_syn_ack(self, SEQ: int) -> bytes:
        """Crea un segmento SYN-ACK con numero de secuencia SEQ, usa la funcion create_segment y retorna bytes. Esta funcion debe ser implementada por ud."""
        return self.create_segment({"SYN":1,"ACK":1,"FIN":0,"SEQ":SEQ,"DATOS":""})

    def create_ack(self, SEQ: int) -> bytes:
        """Crea un segmento ACK con numero de secuencia SEQ, usa la funcion create_segment y retorna bytes. Esta funcion debe ser implementada por ud."""
        return self.create_segment({"SYN":0,"ACK":1,"FIN":0,"SEQ":SEQ,"DATOS":""})

    def create_data_segment(self, SEQ: int, DATA: bytes) -> bytes:
        """Crea un segmento de datos con numero de secuencia SEQ y contenido DATA. Usa la funcion create_segment y retorna bytes. Esta funcion debe ser implementada por ud."""
        return self.create_segment({"SYN":0,"ACK":0,"FIN":0,"SEQ":SEQ,"DATOS":DATA.decode()})

    def check_syn_ack(self, segment: bytes, SEQ: int) -> bool:
        """Checkea si el segmento segment es un SYN-ACK con numero de secuencia SEQ. Esta funcion debe ser implementada por ud."""
        segment = self.parse_segment(segment)
        return segment["SYN"] == 1 and segment["ACK"] == 1 and segment["SEQ"] == SEQ

    def check_ack(self, segment: bytes, expected_seq: int) -> bool:
        """Checkea si el segmento segment es un ACK con numero de secuencia expected_seq. Esta funcion debe ser implementada por ud."""
        segment = self.parse_segment(segment)
        return segment["ACK"] == 1 and segment["SEQ"] == expected_seq

    def check_seq(self, segment: bytes, expected_seq: int) -> bool:
        """Checkea si el segmento segment tiene numero de secuencia expected_seq. Esta funcion debe ser implementada por ud."""
        segment = self.parse_segment(segment)
        return segment["SEQ"] == expected_seq

    def is_valid_ack_go_back_n(self, sliding_window: swcc.SlidingWindowCC, answer: bytes) -> bool:
        """Checkea si el segmento answer tiene numero de secuencia correcto para Go Back N"""
        parsed_answer = self.parse_segment(answer)
        answer_seq = parsed_answer["SEQ"]
        is_ack = parsed_answer["SEQ"]
        for i in range(sliding_window.window_size):
            if is_ack and sliding_window.get_sequence_number(i) == answer_seq:
                return True
        return False

    def update_seq_number(self, length: int):
        """Actualiza el numero de secuencia. Cada vez que se llama el numero de secuencia aumenta en 1 (asume que los numeros de secuencia se rigen por ventanas deslizantes tipo SlidingWindow). """
        self.seq += length

    def bind_to_new_address(self, original_socketTCP_address: (str, int)):
        """Asocia un socket tipo SocketTCP a una diección distinta de original_socketTCP_address. Esta funcion debe ser implementada por ud."""
        self.socket_udp.bind((original_socketTCP_address[0], original_socketTCP_address[1] + self.seq))

    def steps_to_move_go_back_n(self, sender_window: swcc.SlidingWindowCC, received_segment: bytes) -> int:
        """Determina la cantidad de pasos que la ventana deslizante sender_window se debe mover dado que se recibio el segmento receibed_segment."""
        wnd_size = sender_window.window_size
        parsed_segment = self.parse_segment(received_segment)
        seq_num = parsed_segment["SEQ"]
        for i in range(wnd_size):
            if seq_num == sender_window.get_sequence_number(i):
                return i + 1
        else:
            return -1

def create_tcp_msg(msg="", SYN=0, ACK=0, FIN=0, SEQ=0):
    segment = ""
    segment += str(SYN) + "|||"
    segment += str(ACK) + "|||"
    segment += str(FIN) + "|||"
    segment += str(SEQ) + "|||"
    segment += str(msg) 
    return segment