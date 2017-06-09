import os.path
import sys
import traceback
from collections import deque
import socket
import pickle as pkl
from multiprocessing import *
from copy import deepcopy


from subprocess import Popen, PIPE
from shlex import split
import platform
import numpy as np

from math import *
import time
from random import *

from SERVER.components.slack import *
from SERVER.components.world import *

with open("data/config.rah", "r") as config:
    config = config.read().strip().split("\n")
    host = config[0]
    port = int(config[1])
    world_name = config[2]
    slack_enable = int(config[3])
    channel = config[4]
    online = int(config[5])
    whitelist_enable = int(config[6])

# If world doesn't exist
if not os.path.isfile('saves/%s.pkl' % world_name):
    # Generate a new world with the function
    # world_seed,maxHeight,minX,maxX,w,h
    world = generate_world(input("Seed:\n"), 1, 3, 10, 10000, 100)

    # Dumps world to file
    with open('saves/%s.pkl' % world_name, 'wb') as file:
        pkl.dump(world, file)

else:
    world = pkl.load(open('saves/world.pkl', 'rb'))


class Player(object):
    global PlayerData, PlayerUUID, itemLib

    def __init__(self, player_number, player_username):
        self.username = player_username
        self.number = player_number

        self.cord, self.spawnCord, self.inventory, self.hotbar, self.health, self.hunger = self.get_player_info()

        # self.saturation, self.foodLib

    def get_player_info(self):
        try:
            return PlayerData[self.username]
        except KeyError:

            PlayerData[self.username] = [world.spawnpoint, world.spawnpoint,
                                         [[[0, 0] for _ in range(9)] for __ in range(3)],
                                         [[0, 0] for _ in range(9)],
                                         10, 10]

            # rahprint(PlayerData[self.username])
            return PlayerData[self.username]

    def change_spawn(self, spawn_position):
        self.spawnCord = spawn_position[:]

    def change_location(self, cord_change):
        self.cord = cord_change[:]

        rahprint(self.cord)

        return self.cord[0], self.cord[1]

    def change_inventory(self, item, slot, amount):
        self.inventory[slot][0] = self.itemLib[item]
        self.inventory[slot][1] += amount

        if self.inventory[slot][1] == 0:
            self.inventory[slot][0] = 0

    def change_inventory_all(self, cinventory, chotbar):
        self.inventory = deepcopy(cinventory)
        self.hotbar = deepcopy(chotbar)

    def take_damage(self, damage):
        self.health -= damage

        if self.health <= 0:
            self.respawn()

    def update_food(self, food):
        # self.hunger += self.foodLib[food][0]
        # self.satura += self.foodLib[food][0]

        pass

    def respawn(self):
        # self.x = self.spawnx
        # self.y = self.spawny

        self.inventory = [[0, 0] for _ in range(36)]
        self.hotbar = [[0, 0] * 2 for _ in range(36)]
        self.hunger = 10
        self.health = 10
        # self.saturation = 10

    def save(self, block_size):
        return [(self.cord[0] // block_size, self.cord[1] // block_size), self.spawnCord, self.inventory, self.hotbar,
                self.health, self.hunger]


class World:
    def __init__(self, world_name):
        self.overworld = self.load_world(world_name)
        self.spawnpoint = self.get_spawnpoint()

    def load_world(self, worldn):
        return pkl.load(open("saves/" + worldn + ".pkl", "rb"))

    def get_world(self, x, y, size, block_size):

        width, height = size[0] // block_size, size[1] // block_size

        return self.overworld[x - 5:x + width + 5, y - 5:y + height + 5]

    def break_block(self, x, y):
        self.overworld[x, y] = 0

    def place_block(self, x, y, blocktype):
        self.overworld[x, y] = blocktype

    def get_spawnpoint(self):
        x = len(self.overworld) // 2
        spawn_offset = 0
        spawn_found = False
        search_cords = self.overworld[x, :len(self.overworld[x])]

        while not spawn_found:
            for y in range(len(search_cords)):
                if y != 0 and search_cords[y] != 0:
                    spawn_found = True
                    x += spawn_offset
                    y -= 1
                    break

            if spawn_offset < 0:
                spawn_offset = abs(spawn_offset)
            elif spawn_offset > 0:
                spawn_offset = spawn_offset * -1 - 1
            else:
                spawn_offset -= 1

            search_cords = self.overworld[x + spawn_offset, :len(self.overworld[x + spawn_offset])]

        return x, y

    def save(self):
        pkl.dump(self.overworld, open('saves/world.pkl', 'wb'))

def rahprint(text):
    print_enable = False

    if print_enable:
        print(text)

def player_sender(send_queue, server):
    rahprint('Sender running...')

    while True:
        tobesent = send_queue.get()
        try:
            server.sendto(pkl.dumps(tobesent[0], protocol=4), tobesent[1])
        except:
            print(tobesent[0])


def receive_message(message_queue, server):
    rahprint('Server is ready for connection!')

    while True:
        try:
            message = server.recvfrom(1024)
        except:
            continue
        message_queue.put((pkl.loads(message[0]), message[1]))


def commandline_in(commandline_queue, fn):
    rahprint('Ready for input.')
    sys.stdin = os.fdopen(fn)

    while True:
        command = input('[Server]>')
        commandline_queue.put(((10, command), ('127.0.0.1', 0000)))


def heart_beats(message_queue, tick):
    while True:
        time.sleep(.06)
        tick += 1
        if tick % 100 == 0:
            message_queue.put(((100, round(time.time(), 3), tick), ("127.0.0.1", 0000)))
            if tick >= 24000:
                tick = 1


def authenticate(message):
    global online

    if not online:
        return True

    user, token = message

    host, port = 'rahmish.com', 1111

    socket.setdefaulttimeout(10)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SERVERADDRESS = (host, port)
    socket.setdefaulttimeout(None)

    try:
        server.connect(SERVERADDRESS)
        server.send(pkl.dumps([2, [user, token]]))

        while True:

            first_message = pkl.loads(server.recv(4096))

            if first_message[0] == 1:
                server.close()
                return True

            else:
                server.close()
                return False
    except:
        server.close()
        return False

if __name__ == '__main__':
    players = {}
    username_dict = {('127.0.0.1', 0):'Rahbot'}
    player_number = 1

    active_players = []

    playerNDisconnect = deque([])
    move = ''

    PlayerData = {}

    sendQueue = Queue()
    messageQueue = Queue()
    commandlineQueue = Queue()
    itemLib = {}
    username = set()

    if slack_enable:
        config_slack()

    world = World(world_name)

    chests = {}

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((host, port))

    rahprint("Server binded to %s:%i" % (host, port))

    heart_beat = Process(target=heart_beats, args=(messageQueue, 0))  # Change the tick stuff later
    heart_beat.start()

    receiver = Process(target=receive_message, args=(messageQueue, server))
    receiver.start()

    sender = Process(target=player_sender, args=(sendQueue, server))
    sender.start()

    fn = sys.stdin.fileno()
    commandline = Process(target=commandline_in, args=(messageQueue, fn))
    commandline.start()
    cmdIn = ""

    with open('data/motd.rah') as motd:
        motd = choice(motd.read().strip().split('\n'))

    with open('data/whitelist.rah') as whitelist:
        whitelist = whitelist.read().strip().split('\n')

    with open('data/op.rah') as op:
        op = op.read().strip().split('\n')

    with open('data/op_config.rah') as op_commands:
        op_commands = op_commands.read().strip().split('\n')

    while True:
        pickled_message = messageQueue.get()
        message, address = pickled_message
        command = message[0]

        rahprint(pickled_message)

        try:

            # External commands
            if command == 0:
                # Player login and authentication
                # Data: [0,<username>, <token>]

                if whitelist_enable and message[1] in whitelist or not whitelist_enable:

                    if message[1] not in username:

                        if authenticate(message[1:3]):

                            if not playerNDisconnect:
                                PN = player_number
                                player_number += 1
                            else:
                                PN = playerNDisconnect.popleft()

                            playerLocations = {players[x].username: players[x].cord for x in players}

                            players[address] = Player(PN, message[1])
                            username_dict[address] = message[1]
                            sendQueue.put(((0, 10000, 100, str(players[address].cord[0]), str(players[address].cord[1]),
                                            players[address].hotbar, players[address].inventory, playerLocations), address))

                            active_players.append(address)

                            messageQueue.put(((10, "%s has connected to the game" % message[1]), ('127.0.0.1', 0000)))
                            # rahprint('Player %s has connected from %s' % (message[1], address))
                            username.add(message[1])

                            for i in players:
                                if players[i].username != username_dict[address]:
                                    sendQueue.put(((1, username_dict[address], str(players[address].cord[0]),
                                                    str(players[address].cord[1]), False), i))

                        sendQueue.put(((400, (
                            "\n\n\n\n\n\n\n\n\nConnection closed by remote host\n\nCredentials were rejected by\nRahCraft Authentication Service\n(Try logging in again)\n\n")),
                                       address))

                    else:
                        sendQueue.put(((400, (
                            "\n\n\n\n\n\n\n\n\nConnection closed by remote host\n\nUsername currently in use\nIf you recently disconnected, wait\n 30 seconds for server to sync")),
                                       address))
                else:
                    sendQueue.put(((400, (
                        "\n\n\n\n\n\n\n\n\nConnection closed by remote host\n\nThis server is white listed\nIf you believe this is an error,\nContact the administrator for assistance")),
                                   address))

            # External heartbeat
            elif command == 102:
                sendQueue.put(((102, motd, host, port), address))

            elif address in players or address == ('127.0.0.1', 0000):
                if command == 1:


                    # Player movement
                    # Data: [1, <cordx>, <cordy>]
                    x, y = players[address].change_location((message[1], message[2]))

                    for i in players:
                        sendQueue.put(((1, username_dict[address], x, y), i))

                elif command == 2:
                    # Render world
                    # Data: [2, <cordx>, <cordy>, <size>]
                    sendQueue.put(((2, message[1], message[2], world.get_world(message[1], message[2], message[3], message[4])), address))

                elif command == 3:
                    # Break block
                    # Data: [3, <cordx>, <cordy>]
                    if hypot(world.spawnpoint[0] - message[1], world.spawnpoint[1] - message[2]) < 5:
                        spawnpoint_check = world.get_spawnpoint()

                        if spawnpoint_check != world.spawnpoint:
                            world.spawnpoint = spawnpoint_check[:]

                            for i in players:
                                players[i].change_spawn(world.spawnpoint)

                    world.break_block(message[1], message[2])

                    for i in players:
                        sendQueue.put(((3, message[1], message[2]), i))

                elif command == 4:
                    # Place block
                    # Data: [4, <cordx>, <cordy>, <block type>]
                    if hypot(world.spawnpoint[0] - message[1], world.spawnpoint[1] - message[2]) < 5:
                        spawnpoint_check = world.get_spawnpoint()

                        if spawnpoint_check != world.spawnpoint:
                            world.spawnpoint = spawnpoint_check[:]

                            for i in players:
                                players[i].change_spawn(world.spawnpoint)

                    world.place_block(message[1], message[2], message[3])
                    players[address].hotbar[message[4]][1] -= 1

                    if players[address].hotbar[message[4]][1] == 0:
                        players[address].hotbar[message[4]] = [0, 0]

                    sendQueue.put(((6, message[4], players[address].hotbar[message[4]]), address))
                    '''
                    if message[3] ==
                    '''
                    for i in players:
                        sendQueue.put(((4, message[1], message[2], message[3]), i))

                elif command == 5:
                    players[address].change_inventory_all(message[1], message[2])

                elif command == 9:

                    messageQueue.put(((10, "%s has disconnected from the game"%username_dict[address]), ('127.0.0.1', 0000)))
                    #rahprint('Player %s has disconnected from the game. %s' % (username_dict[address], address))

                    playerNDisconnect.append(players[address].number)
                    PlayerData[username_dict[address]] = players[address].save(message[1])
                    offPlayer = username_dict[address]
                    username.remove(offPlayer)

                    del players[address]
                    del username_dict[address]

                    for i in players:
                        sendQueue.put(((9, offPlayer), i))

                elif command == 10:

                    send_message = ''

                    if message[1].lower()[0] == '/':
                        if (message[1].lower().split(' ')[0][1:] in op_commands and address in players and username_dict[address] in op) or message[1].lower().split(' ')[0][1:] not in op_commands or address == ('127.0.0.1', 0):

                            if message[1].lower() == "/quit":
                                receiver.terminate()
                                sender.terminate()
                                commandline.terminate()
                                heart_beat.terminate()
                                server.close()
                                world.save()
                                break

                            elif message[1].lower() == "/delworld":
                                send_message = "<Rahmish Empire> CONFIRM: DELETE WORLD? THIS CHANGE IS PERMANENT (y/n) [n]: "

                                sys.stdout.flush()
                                in_put = messageQueue.get()
                                while in_put[0][0] != 10:
                                    # rahprint(in_put)
                                    in_put = messageQueue.get()

                                if in_put[0][1] == 'y':
                                    os.remove("saves/world.pkl")
                                    send_message = "World deleted successfully\nServer will shutdown"
                                    receiver.terminate()
                                    sender.terminate()
                                    commandline.terminate()
                                    server.close()

                                    exit()

                                    break

                                else:
                                    send_message = "Command aborted"

                            elif message[1].lower() == '/ping':
                                send_message = 'pong!'

                            elif message[1].lower() == '/lenin':
                                with open('data/communist.rah') as communist:
                                    for line in communist.read().split('\n'):
                                        send_message = '[Comrade Lenin] ' + line

                                        for i in players:
                                            sendQueue.put(((10, send_message), i))

                            elif message[1].lower()[:4] == '/say':
                                send_message =  message[1][4:]

                            elif message[1].lower()[:6] == '/clear':
                                players[address].inventory =[[[randint(1, 15), randint(1, 64)] for _ in range(9)] for __ in range(3)]
                                players[address].hotbar = [[8, 64] for _ in range(9)]

                            elif message[1].lower()[:5] == '/give':

                                message_list = message[1].split(' ')

                                executor = username_dict[address]
                                receiver = message_list[1]
                                item, quantity = message_list[2:4]

                                for player in players:
                                    if players[player].username == receiver:
                                        players[player].hotbar[0] = [int(item), int(quantity)]
                                        players[player].change_inventory_all(players[player].inventory, players[player].hotbar)

                                send_message = '%s gave %s %s of %s'%(executor, receiver, quantity, item)

                            elif message[1].lower()[:5] == '/kick':

                                kick_name = message[1][6:]

                                for player in players:
                                    if players[player].username == kick_name:
                                        sendQueue.put(((11, '\n\n\nDisconnected from server by %s'%username_dict[address]), player))
                                        send_message = '%s was disconnected from the server by %s'%(kick_name, username_dict[address])

                                if not send_message:
                                    send_message = 'Player %s not found'%kick_name


                            elif message[1].lower()[:3] == '/tp':

                                message_list = message[1].split(' ')
                                executor = username_dict[address]
                                receiver = message_list[1]

                                for player in players:
                                    if players[player].username == receiver:

                                        x, y = players[player].change_location((list(map(int, message_list[2:4]))))

                                        for i in players:
                                            sendQueue.put(((1, players[player].username, x, y, True), i))

                                send_message = '%s teleported %s to %s %s' % (executor, receiver, x, y)

                            elif message[1].lower()[:3] == '/op':

                                message_list = message[1].split(' ')

                                if len(message_list) == 3:

                                    executor = username_dict[address]
                                    receiver = message_list[2]

                                    if message_list[1] == 'add':
                                        op.append(receiver)
                                        send_message = '%s gave %s op'%(executor, receiver)

                                        with open('data/op.rah', 'w') as op_file:
                                            for user in op:
                                                op_file.write('%s\n'%user)

                                    elif message_list[1] == 'remove':
                                        if receiver in op:
                                            del op[op.index(receiver)]

                                            with open('data/op.rah', 'w') as op_file:
                                                for user in op:
                                                    op_file.write('%s\n' % user)

                                            send_message = 'User %s was removed from the op list' % receiver
                                        else:
                                            send_message = 'User %s was not found in the op list'%receiver

                                    else:
                                        send_message = 'Unknown subcommand %s'%message_list[1]

                                else:
                                    send_message = 'No parameters given'

                            elif message[1].lower()[:10] == '/whitelist':

                                message_list = message[1].split(' ')

                                if len(message_list) == 2:
                                    if message_list[1] == 'toggle':
                                        whitelist_enable = not whitelist_enable

                                        if whitelist_enable:
                                            send_message = 'Whitelist enabled by %s'%username_dict[address]
                                        else:
                                            send_message = 'Whitelist disabled by %s' % username_dict[address]

                                        with open("data/config.rah", "w") as config_file:

                                            config = config.read().strip().split("\n")
                                            config_list = [host,
                                                           port,
                                                           world_name,
                                                           slack_enable,
                                                           channel,
                                                           online,
                                                           whitelist_enable]

                                            for line in config_list:
                                                config_file.write(line + '\n')


                                elif len(message_list) == 3:

                                    executor = username_dict[address]
                                    receiver = message_list[2]

                                    if message_list[1] == 'add':
                                        whitelist.append(receiver)
                                        send_message = '%s added %s to the whitelist'%(executor, receiver)

                                        with open('data/whitelist.rah', 'w') as whitelist_file:
                                            for user in whitelist:
                                                whitelist_file.write('%s\n'%user)

                                    elif message_list[1] == 'remove':
                                        if receiver in whitelist:
                                            del whitelist[whitelist.index(receiver)]

                                            with open('data/whitelist.rah', 'w') as whitelist_file:
                                                for user in whitelist:
                                                    whitelist_file.write('%s\n' % user)

                                            send_message = 'User %s was removed from the whitelist' % receiver
                                        else:
                                            send_message = 'User %s was not found in the whitelist'%receiver

                                    else:
                                        send_message = 'Unknown subcommand %s'%message_list[1]

                                else:
                                    send_message = 'No parameters given'

                            elif message[1].lower()[:5] == '/exec':
                                try:
                                    exec(message[1][6:])
                                    send_message = "Command '%s' executed by %s" % (message[1][6:], username_dict[address])
                                except:
                                    send_message = "Command '%s' failed to execute: %s" % (message[1][6:], traceback.format_exc().replace('\n',''))

                            elif message[1].lower()[:5] == '/bash':

                                try:
                                    rahprint(Popen(split(message[1][6:]), stdout=PIPE))
                                    send_message = "Bash command '%s' executed by %s" % (message[1][6:], username_dict[address])
                                except:
                                    send_message = "Bash command '%s' failed to execute: %s" % (message[1][6:], traceback.format_exc().replace('\n',''))

                            elif message[1].lower()[:5] == '/sync':
                                messageQueue.put(((100, round(time.time(), 3), 0), ("127.0.0.1", 0000)))
                                send_message = "Server synchronized"

                            elif message[1].lower()[:5] == '/list':
                                send_message = str(players)

                            else:
                                send_message = "Command not found"

                        else:
                            send_message = "Access denied"

                    else:
                        user_sending = username_dict[address]

                        send_message = '[%s] %s' % (user_sending, message[1])

                    if send_message[0] != '[':
                        send_message = '[%s] '%username_dict[('127.0.0.1', 0)] + send_message

                    for i in players:
                        sendQueue.put(((10, send_message), i))

                    if slack_enable:
                        broadcast(channel, send_message)

                elif command == 100:

                    kill_list = []

                    for p in players:
                        if p in active_players:
                            for repeat in range(5):
                                sendQueue.put((message, p))

                        else:
                            kill_list.append(p)

                    for p in kill_list:

                        send_message = '[Server] %s was disconnected for not responding' % (players[p].username)

                        for i in players:
                            sendQueue.put(((10, send_message), i))

                        if slack_enable:
                            broadcast(channel, send_message)

                        playerNDisconnect.append(players[p].number)
                        PlayerData[players[p].username] = players[p].save(message[1])
                        offPlayer = players[p].username
                        username.remove(offPlayer)

                        del players[p]
                        del username_dict[p]

                        for i in players:
                            sendQueue.put(((9, offPlayer), i))

                    broadcast(channel, '[Tick] %s' % message[2])

                    active_players = []

                elif command == 101:
                    if address not in active_players:
                        active_players.append(address)
                    rahprint('[Server] %s has responded to heartbeat' % message[1])

            else:
                sendQueue.put(((11, '\n\n\nDisconnected from server\n\nAccess denied'), address))


        except:
            sendQueue.put(((11, '\n\n\nDisconnected from server'), address))

            print(traceback.format_exc())
