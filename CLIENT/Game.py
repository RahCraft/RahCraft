# RAHCRAFT
# COPYRIGHT 2017 (C) RAHMISH EMPIRE, MINISTRY OF RAHCRAFT DEVELOPMENT
# DEVELOPED BY RYAN ZHANG, HENRY TU, SYED SAFWAAN

# game.py

import os, sys, traceback, platform, glob, socket, pickle, \
    json  # Libraries required for the proper operation of the game

from subprocess import Popen, PIPE
from shlex import split
from multiprocessing import *  # Multiprocessing for help with sending and receiving data
import numpy as np  # Numpy used to decode the numpy array that the server sends
from math import *
from copy import deepcopy  # Obtain the ability to duplicate multi dimensional lists
import time as ti
from pygame import *
from random import *

import components.rahma as rah  # Group made packages required for the game to function
import components.player as player
import components.menu as menu


# The sender gets messages from the send queue and sends it to the server for processing
# This multiprocessing is needed to handle delay due to upload speed
def player_sender(send_queue, server):
    rah.rahprint('Sender running...')

    while True:
        tobesent = send_queue.get()  # Get message from queue
        server.sendto(pickle.dumps(tobesent[0], protocol=4),
                      tobesent[1])  # Send a pickled message/message in bytes to server


# Receiving messages from the server.
# Multiprocessing is needed becauase a extremely fast loop is needed to accept the data to prevent data lost

def receive_message(message_queue, server):
    rah.rahprint('Ready to receive command...')

    while True:
        msg = server.recvfrom(163840)  # Recieving data from server
        message_queue.put(pickle.loads(msg[0]))  # Puts the data in a queue for processing


# Loads the blocks that can be placed in the world
def load_blocks(block_file, block_size):
    blocks = {}  # A place where all of the blocks will be stored

    block_data = json.load(open("data/" + block_file))  # Loads the data file

    for block in block_data:  # Loops through the data extracting data and loading the images
        blocks[int(block)] = {'name': block_data[block]['name'],
                              'texture': transform.scale(
                                  image.load("textures/blocks/" + block_data[block]['texture']).convert_alpha(),
                                  (block_size, block_size)),
                              'hardness': block_data[block]['hardness'],
                              'sound': block_data[block]['sound'],
                              'collision': block_data[block]['collision'],
                              'icon': transform.scale(
                                  image.load("textures/icons/" + block_data[block]['icon']).convert_alpha(), (32, 32)),
                              'tool': block_data[block]['tool'],
                              'drop': block_data[block]['drop'],
                              'tool-required': True if block_data[block]['tool-required'] == 1 else False,
                              'maxstack': block_data[block]['maxstack']}

    return blocks


# Same as the block loading function but for tools.
def load_tools(tool_file):
    tools = {}

    tool_data = json.load(open("data/" + tool_file))

    for tool in tool_data:  # Run through the tools file using a loop load images
        tools[int(tool)] = {'name': tool_data[tool]['name'],
                            'icon': transform.scale(
                                image.load("textures/items/" + tool_data[tool]['icon']).convert_alpha(), (32, 32)),
                            'bonus': tool_data[tool]['bonus'],
                            'speed': tool_data[tool]['speed'],
                            'type': tool_data[tool]['type'],
                            'durability': tool_data[tool]['durability'],
                            'maxstack': 1}

    return tools


# Creating a dictionary of items for later processing
def load_items(item_file):
    items = {}

    item_data = json.load(open("data/" + item_file))  # Loads json

    for item in item_data:
        items[int(item)] = {'name': item_data[item]['name'],
                            'icon': transform.scale(
                                image.load("textures/items/" + item_data[item]['icon']).convert_alpha(), (32, 32)),
                            'maxstack': item_data[item]['maxstack']}

    return items


def create_item_dictionary(*libraries):  # Creating a central item library inventory rendering
    item_lib = {}

    for di in libraries:  # Loop through each of the inventory provided and pick out the needed values for inventory to operate
        for item in di:
            item_lib[item] = [di[item]['name'], di[item]['icon'], di[item]['maxstack']]

    return item_lib


def commandline_in(commandline_queue, fn, address, chat_queue):  # Chat
    rah.rahprint('Ready for input.')  # Smalling debugging function
    sys.stdin = os.fdopen(fn)  # Opens the input stream

    while True:  # Waits for input
        commandline_queue.put(((10, chat_queue.get()), address))


def pickup_item(inventory, hotbar, Nitem, item_lib):  # This function helps find a space to put the item
    item_location = ''  # used to store the first location where the item can be stored
    inventory_type = ''  # This is used to store the first open slot type (inventory or hotbar)
    for item in range(len(hotbar)):  # Loop through the hotbar first because the hotbar takes priority
        if hotbar[item][0] == Nitem and hotbar[item][1] < item_lib[hotbar[item][0]][
            2]:  # If stacking is possible, stack item and quit
            hotbar[item][1] += 1
            return inventory, hotbar
        elif hotbar[item][
            0] == 0 and inventory_type == '':  # If an open space is found, store the cords and type for later use if not valid stacking spot is found
            item_location = item
            inventory_type = 'hotbar'

    for row in range(len(inventory)):  # Same as above but searches through the inventory instead
        for item in range(len(inventory[row])):
            if inventory[row][item][0] == Nitem and inventory[row][item][1] < item_lib[inventory[row][item][0]][2]:
                inventory[row][item][1] += 1
                return inventory, hotbar
            elif inventory[row][item][0] == 0 and inventory_type == '':
                item_location = [row, item]
                inventory_type = 'inventory'

    if inventory_type == 'hotbar':  # If no place to stack the inventory is found, place the item(s) in the first open slot found
        hotbar[item_location] = [Nitem, 1]
    elif inventory_type == 'inventory':
        inventory[item_location[0]][item_location[1]] = [Nitem, 1]

    return inventory, hotbar


# Main game function
def game(surf, username, token, host, port, size):
    def quit_game():  # A function that quits all of the processes, sends the quit command to the server and stops the music
        music_object.stop()  # Stop music
        send_queue.put(((9,), SERVERADDRESS))
        time.wait(50)  # Waits for the server to process and broadcast the info to other players
        sender.terminate()
        receiver.terminate()
        commandline.terminate()

    # Gets blocks surrounding the player
    def get_neighbours(x, y):
        """Gets the neighbouring blocks"""
        return [world[x + 1, y], world[x - 1, y], world[x, y + 1], world[x, y - 1]]

    # Renders the blocks in the world
    def render_world():
        """Rendering the world and the block breaking animation"""
        for x in range(0, size[0] + block_size + 1,
                       block_size):  # Render and area of the world using a for loop since the world is in a 2d array
            for y in range(0, size[1] + block_size + 1, block_size):
                block = world[(x + x_offset) // block_size][(y + y_offset) // block_size]  # Gets the current block

                if len(block_properties) > block > 0:  # If the block is not air and is not a unknown block
                    surf.blit(block_properties[block]['texture'],
                              (x - x_offset % block_size, y - y_offset % block_size))  # Blit texture

                    if breaking_block and current_breaking[1] == (x + x_offset) // block_size \
                            and current_breaking[2] == (
                                        y + y_offset) // block_size:  # Checks if a block is being broken
                        percent_broken = (current_breaking[3] / block_properties[current_breaking[0]][
                            'hardness']) * 10  # calculate percentage of the block broken
                        surf.blit(breaking_animation[int(percent_broken)],
                                  (x - x_offset % block_size, y - y_offset % block_size))  # Blit correct image

    def render_hotbar(hotbar_slot):
        """Renders the hotbar"""
        surf.blit(hotbar, hotbar_rect)  # draws hotbar graphics
        for item in range(9):  # Loops through the list drawing each item
            if hotbar_items[item][1] != 0:  # If the hotbar is not blank
                surf.blit(item_lib[hotbar_items[item][0]][1],
                          (hotbar_rect[0] + (32 + 8) * item + 6, size[1] - 32 - 6))  # Blit image
                if hotbar_items[item][1] > 1:  # Add a number if the amount of items in that slot is greater than one
                    surf.blit(rah.text(str(hotbar_items[item][1]), 10),
                              (hotbar_rect[0] + (32 + 8) * item + 6, size[1] - 32 - 6))

            if len(hotbar_items[item]) == 3:  # If an extra meta data is provided
                draw.rect(surf, (0, 0, 0), (
                    hotbar_rect[0] + (32 + 8) * item + 10, size[1] - 10, 24, 2))  # Creates a bar to display durability
                draw.rect(surf, (255, 255, 0), (hotbar_rect[0] + (32 + 8) * item + 10, size[1] - 10, int(
                    24 * hotbar_items[item][2] // tool_properties[hotbar_items[item][0]]['durability']),
                                                2))  # Calculate the bar using the max durabilty

        surf.blit(selected,
                  (hotbar_rect[0] + (32 + 8) * hotbar_slot, size[1] - 32 - 12))  # Blit the slot selected for feed back

        # Blit the block name if the item is not 0
        if hotbar_items[hotbar_slot][0] != 0:
            block_name = rah.text(str(item_lib[hotbar_items[hotbar_slot][0]][0]), 13)
            surf.blit(block_name, (size[0] // 2 - block_name.get_width() // 2, size[1] - 80))

    # Loading Screen
    # =====================================================================
    display.set_caption("RahCraft")

    # Setting Up Socket I/O and Multiprocessing
    # =====================================================================
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP socket
    SERVERADDRESS = (host, port)

    send_queue = Queue()  # Queues for cross process communication
    message_queue = Queue()
    chat_queue = Queue()

    # Starting processes
    sender = Process(target=player_sender, args=(send_queue, server))
    sender.start()

    receiver = Process(target=receive_message, args=(message_queue, server))
    receiver.start()

    fn = sys.stdin.fileno()  # Gets the io number for connecting the input stream of the main input to the input stream of the child process
    commandline = Process(target=commandline_in, args=(send_queue, fn, SERVERADDRESS, chat_queue))
    commandline.start()
    cmd_in = ""

    block_size = 50  # Set the default block size
    build = 'RahCraft v0.1.1 EVALUATION'  # A build version for reference

    # Chat
    # =====================================================================
    chat = menu.TextBox(20, size[1] - 120, size[0] - 50, 40, '')
    chat_content = ''
    chat_list = []

    # Loading Textures
    # =====================================================================
    block_properties = load_blocks("block.json", block_size)
    tool_properties = load_tools("tools.json")
    item_properties = load_items("items.json")

    item_lib = create_item_dictionary(block_properties, tool_properties, item_properties)
    rah.rahprint(item_lib)
    breaking_animation = [
        transform.scale(image.load("textures/blocks/destroy_stage_" + str(i) + ".png"),
                        (block_size, block_size)).convert_alpha() for i
        in range(10)]  # Loading and transforming the block breaking animations to the correct size

    health_texture = {"none": image.load("textures/gui/icons/heart_none.png"),
                      "half": image.load("textures/gui/icons/heart_half.png"),
                      "full": image.load("textures/gui/icons/heart_full.png")}  # Loads the required images for health

    hunger_texture = {"none": image.load("textures/gui/icons/hunger_none.png"),
                      "half": image.load("textures/gui/icons/hunger_half.png"),
                      "full": image.load("textures/gui/icons/hunger_full.png")}  # Loads the hunger images

    tint = Surface(size)  # A tint surface for effects when opening inventory
    tint.fill((0, 0, 0))
    tint.set_alpha(99)

    # Receiving First Messages, Initing World, and Player
    # =====================================================================

    clock = time.Clock()  # Setting pygame.time.Clock() to a simpler name for easier calling
    dir = 10  # The direction that the loading bar slide moves and the speed
    slider_x = 0  # The x location of the loading bar

    for cycle in range(1001):  # A for loop is used to prevent the loss of important messages
        try:  # Try and except is needed here because the server address can be invalid
            server.sendto(pickle.dumps([0, username, token]), SERVERADDRESS)  # Send first login message to server
        except:
            return 'information', '\n\n\n\n\nUnable to connect to server\nHost or Port invalid', 'server_picker'

        if cycle == 1000:  # Cannot connect to the server
            return 'information', '\n\n\n\n\nUnable to connect to server\nTimed out', 'server_picker'

        # Creating a loading screen while waiting for message from server
        rah.wallpaper(surf, size)

        connecting_text = rah.text("Connecting to %s:%i..." % (host, port), 15)

        surf.blit(connecting_text,
                  rah.center(0, 0, size[0], size[1], connecting_text.get_width(), connecting_text.get_height()))

        tile_w = size[0] // 8

        slider_x += dir

        if slider_x <= 0 or slider_x >= size[
            0] // 2 - tile_w:  # Change the direction of the slider if the reaches the end
            dir *= -1

        draw.rect(surf, (0, 0, 0), (size[0] // 4, size[1] // 2 + 40, size[0] // 2, 10))
        draw.rect(surf, (0, 255, 0), (size[0] // 4 + slider_x, size[1] // 2 + 40, tile_w, 10))

        display.update()  # Update the pygame window to show changes

        try:  # The queue may be empty
            first_message = message_queue.get_nowait()  # Get the first message

            if first_message[0] == 400 or not first_message[1:]:  # Message returned with a failure
                sender.terminate()  # End the game
                receiver.terminate()
                commandline.terminate()
                return 'information', first_message[1], 'server_picker'
            elif first_message[0] == 0:  # If login is successful
                break

        except:
            pass

        clock.tick(15)  # set a frame rate to prevent client from overloading the server

    # Retreving information from the message
    world_size_x, world_size_y, player_x_, player_y_, hotbar_items, inventory_items, r_players, health, hunger = first_message[
                                                                                                                 1:]

    rah.rahprint("player done")

    reach = 5  # The max number of blocks that the user can reach

    player_x = int(float(player_x_) * block_size)  # Calculates the actural pixel location of the player
    player_y = int(float(player_y_) * block_size)

    world = np.array([[-1] * (world_size_y + 40) for _ in
                      range(world_size_x)])  # Creates a blank world with some to spare for world loading

    local_player = player.Player(player_x, player_y, (2 * block_size - 1 - 1) // 4, 2 * block_size - 1 - 1, block_size,
                                 (K_a, K_d, K_w, K_s, K_SPACE))  # Creating local player

    x_offset = local_player.rect.x - size[0] // 2 + block_size // 2  # Getting a offset of the part of the world to get
    y_offset = local_player.rect.y - size[1] // 2 + block_size // 2

    remote_players = {}
    x, y = 0, 0

    for cycle in range(
            1001):  # Important message again. Requesting world from the server. For loop prevents data loss by sending it multiple times
        if cycle == 1000:
            return 'information', '\n\n\n\n\nServer took too long to respond\nTimed out', 'server_picker'

        send_queue.put([[2, x_offset // block_size, y_offset // block_size, size, block_size], SERVERADDRESS])
        # Loading screen with animations like above
        rah.wallpaper(surf, size)

        connecting_text = rah.text("Downloading world...", 15)

        surf.blit(connecting_text,
                  rah.center(0, 0, size[0], size[1], connecting_text.get_width(), connecting_text.get_height()))

        tile_w = size[0] // 8

        slider_x += dir

        if slider_x <= 0 or slider_x >= size[0] // 2 - tile_w:
            dir *= -1

        draw.rect(surf, (0, 0, 0), (size[0] // 4, size[1] // 2 + 40, size[0] // 2, 10))
        draw.rect(surf, (0, 255, 0), (size[0] // 4 + slider_x, size[1] // 2 + 40, tile_w, 10))

        display.update()

        try:
            world_msg = message_queue.get_nowait()

            if world_msg[0] == 2:  # Message correctly recieved
                world[world_msg[1] - 5:world_msg[1] + size[0] // block_size + 5,
                world_msg[2] - 5:world_msg[2] + size[1] // block_size + 5] = np.array(world_msg[3], copy=True)

                break

            elif world_msg[0] == 100:  # Heartbeat
                send_time, tick = world_msg[1:]  # Sets the tick

                tick_offset = (round(ti.time(), 3) - send_time) * 20

                sky_tick = tick_offset + tick

                for repeat in range(3):  # Reply stating that his player is active
                    send_queue.put(([(101, username), SERVERADDRESS]))

        except:
            pass

        clock.tick(15)

    # Init Existing Remote Players
    # =====================================================================
    for Rp in r_players:
        remote_players[Rp] = player.RemotePlayer(Rp, r_players[Rp][0], r_players[Rp][1],
                                                 (2 * block_size - 1 - 1) // 4, 2 * block_size - 1 - 1)

    # Initing Ticks and Sky
    # =====================================================================
    TICKEVENT = USEREVENT + 1
    tick_timer = time.set_timer(TICKEVENT, 50)
    current_tick = 0

    sun = transform.scale(image.load("textures/sky/sun.png"), (100, 100))
    moon = transform.scale(image.load("textures/sky/moon.png"), (100, 100))
    sky_tick = 1

    SKYTICKDEFAULT = 120

    # Initing Anti-Lag
    # =====================================================================
    block_request = set()
    render_request = set()
    old_location = [local_player.rect.x, local_player.rect.y]

    # Initing Pausing/Inventories
    # =====================================================================
    paused = False

    fly = False
    inventory_visible = False
    chat_enable = False
    debug = False

    text_height = rah.text("QWERTYRAHMA", 10).get_height()

    pause_list = [[0, 'unpause', "Back to game"],
                  [1, 'options', "Options"],
                  [2, 'menu', "Exit"]]

    pause_menu = menu.Menu(pause_list, 0, 0, size[0], size[1])

    # Initing Block Breaking
    # =====================================================================
    current_breaking = []
    breaking_block = False

    # Init Inventory
    # =====================================================================
    hotbar = image.load("textures/gui/toolbar/toolbar.png").convert()
    selected = image.load("textures/gui/toolbar/selected.png").convert_alpha()

    normal_font = font.Font("fonts/minecraft.ttf", 14)

    inventory_object = menu.Inventory(size[0], size[1])

    hotbar_rect = (size[0] // 2 - hotbar.get_width() // 2, size[1] - hotbar.get_height())
    hotbar_slot = 0

    INVENTORY_KEYS = {str(x) for x in range(1, 10)}

    # Initing Sound
    # =====================================================================
    sound_types = [stype[6:-1] for stype in glob.glob('sound/*/')]

    sound = {sound_type: {} for sound_type in sound_types}

    for stype in sound_types:  # Iterating through every sound type loading it

        sound_list = glob.glob('sound/%s/*.ogg' % stype)  # Searches directories for sounds

        sound_blocks = [sound.replace('\\', '/').split("/")[-1][:-5] for sound in sound_list]  # Changes slash direction (Windows and Linux differs)

        for block in sound_blocks:  # loading the different block sounds
            local_sounds = []

            for sound_dir in sound_list:
                if block in sound_dir:
                    local_sounds.append(sound_dir)

            sound[stype][block] = local_sounds

    block_step = None  # Sound of block currently below user

    music_object = mixer.Sound('sound/music/bg4.wav')  # play some background music
    music_object.play(1, 0)

    damage_list = glob.glob('sound/damage/*.ogg')  # Getting a list of all the damage sounds

    # Crafting/other gui stuffz
    # =====================================================================

    crafting_object = menu.Crafting(size[0], size[1])  # In game inventory stuff
    chest_object = menu.Chest(size[0], size[1])
    furnace_object = menu.Furnace(size[0], size[1])

    crafting = False  # UI states
    using_chest = False
    using_furnace = False

    current_gui = ''  # A var to define which inventory is being used
    current_chest = []  # Current interactive block selected
    current_furnace = []
    chest_location = []

    # Block highlight
    # =====================================================================
    highlight_good = Surface((block_size, block_size))  # block is in range of the player's reach
    highlight_good.fill((255, 255, 255))
    highlight_good.set_alpha(50)

    highlight_bad = Surface((block_size, block_size))  # block is not in range of the player's reach
    highlight_bad.fill((255, 0, 0))
    highlight_bad.set_alpha(90)
    inventory_updated = False

    # Sky and stars
    # ======================================================================
    sky_diming = False

    star_list = [[randint(0, size[0]), randint(0, size[1])] for star in range(size[0] // 10)]

    # Main game loop
    try:
        while True:

            # Initialize and declare game control variables
            release = False  # release mouse button
            on_tick = False  # keep track of ticks
            block_broken = False  # to break blocks
            tick_per_frame = max(clock.get_fps() / 20, 1)  # for player interpol
            r_click = False  # right clicks
            l_click = False  # left_clicks
            pass_event = None  # for chat

            # Event loop
            for e in event.get():  # for every event in the EventQueue

                #  Retrieve event every frame
                pass_event = e

                # Check to see what event the user has initiated
                if e.type == QUIT:  # if user wants to quit

                    # Break out of game
                    quit_game()
                    return 'menu'

                elif e.type == MOUSEBUTTONDOWN and not paused:  # if user clicked mouse button

                    # Check to see what button user hit

                    if e.button == 1:  # if user left clicked
                        l_click = True  # user has left clicked
                    if e.button == 3:  # if user has right clicked
                        r_click = True  # user has right clicked

                    if e.button == 4:  # if user scrolled up

                        # Change the current hotbar slot
                        hotbar_slot = max(-1, hotbar_slot - 1)
                        if hotbar_slot == -1:  # if user goes over the end of the hotbar
                            hotbar_slot = 8  # set back to normal

                    elif e.button == 5:  # if user scrolled down

                        # Change the current hotbar slot
                        hotbar_slot = min(9, hotbar_slot + 1)
                        if hotbar_slot == 9:  # if user goes over the end of the hotbar
                            hotbar_slot = 0  # set back to normal

                elif e.type == MOUSEBUTTONUP and e.button == 1:  # if user released left click

                    # The user has released the mouse button
                    release = True

                elif e.type == KEYDOWN:  # if the user hit a keyboard key

                    # Check to see what user hit

                    if e.key == K_F3:  # if user hit F3

                        # Toggle debug menu
                        debug = not debug

                    if e.key in [K_SLASH, K_t] and not current_gui:  # if user hit a chat init button

                        # Enable chat box
                        chat_enable = True
                        current_gui = 'CH'

                    if chat_enable and e.key == K_RETURN:  # if user hits enter in chat box

                        # Place entered text on queue
                        chat_queue.put(chat_content)

                        # Wipe the chat box and disable chat
                        chat.content = ''
                        chat_enable = False
                        current_gui = ''

                    if e.key == K_ESCAPE:  # if user hit ESCAPE

                        # Check to see what UI the player was on
                        # For all of these, just reset menu to normal

                        if current_gui == 'C':  # if player was crafting
                            inventory_updated = True
                            crafting = False
                            current_gui = ''
                        elif current_gui == 'I':  # if player was in inventory screen
                            inventory_updated = True
                            inventory_visible = False
                            current_gui = ''
                        elif current_gui == 'CH':  # if user was in chat box
                            chat.content = ''
                            chat_enable = False
                            current_gui = ''
                        elif current_gui == 'Ch':  # if user was in chest menu
                            send_queue.put(((7, 'chest', chest_location[0], chest_location[1], 0), SERVERADDRESS))
                            using_chest = False
                            current_chest = []
                            current_gui = ''
                            inventory_updated = True
                        elif current_gui == 'F':  # if user was in furnace menu
                            send_queue.put(((7, 'furnace', furnace_location[0], furnace_location[1], 0), SERVERADDRESS))
                            using_furnace = False
                            current_furnace = []
                            current_gui = ''
                            inventory_updated = True
                        elif current_gui == '' or current_gui == 'P':  # if user was not in any menu, or paused

                            # Toggle pause screen
                            paused = not paused
                            if paused:
                                current_gui = 'P'
                            else:
                                current_gui = ''

                    elif not paused and current_gui != 'CH':  # if user hit another key, and wasn't in chat

                        # Check to see what the user hit

                        if e.unicode in INVENTORY_KEYS:  # if user hit a number of the number row

                            # Change the current hotbar slot
                            hotbar_slot = int(e.unicode) - 1

                        if e.key == K_f and debug:  # if the user hit 'F'

                            # Toggle flying
                            fly = not fly

                        if e.key == K_e and current_gui in ['', 'I']:  # if user hit 'E'

                            # Check to see if user was in the inventory already
                            if current_gui == 'I':  # if user was in inventory menu

                                # Update inventory
                                inventory_updated = True

                            # Toggle inventory screen
                            inventory_visible = not inventory_visible
                            if inventory_visible:
                                current_gui = 'I'
                            else:
                                current_gui = ''

                # Resize window
                elif e.type == VIDEORESIZE:

                    # Limits window size
                    rw, rh = max(e.w, 657), max(e.h, 505)

                    surf = display.set_mode((rw, rh), RESIZABLE)
                    size = ((rw, rh))

                    # Redraws elements
                    chat = menu.TextBox(20, size[1] - 120, size[0] - 50, 40, '')
                    pause_menu = menu.Menu(pause_list, 0, 0, size[0], size[1])
                    inventory_object = menu.Inventory(size[0], size[1])
                    hotbar_rect = (size[0] // 2 - hotbar.get_width() // 2, size[1] - hotbar.get_height())
                    crafting_object = menu.Crafting(size[0], size[1])
                    furnace_object = menu.Crafting(size[0], size[1])

                    star_list = [[randint(0, size[0]), randint(0, size[1])] for star in range(size[0] // 10)]

                    tint = Surface(size)
                    tint.fill((0, 0, 0))
                    tint.set_alpha(99)

                # Game tick counter
                elif e.type == TICKEVENT:
                    event.clear(TICKEVENT)
                    tick_timer = time.set_timer(TICKEVENT, 50)

                    on_tick = True
                    current_tick += 1
                    if current_tick == 20:
                        current_tick = 0

            # Gets player's location in the world based on their pixel location and block size
            x_offset = local_player.rect.x - size[0] // 2 + block_size // 2
            y_offset = local_player.rect.y - size[1] // 2 + block_size // 2

            # Gets the player's snapped block location
            block_clip = (local_player.rect.centerx // block_size * block_size, local_player.rect.centery // block_size * block_size)
            offset_clip = Rect((x_offset // block_size, y_offset // block_size, 0, 0))

            # Tell server inventory has been modified
            if inventory_updated:
                send_queue.put(([(5, inventory_items, hotbar_items), SERVERADDRESS]))
                inventory_updated = False

            # Player movement
            if current_tick % 2 == 0 and [local_player.rect.x, local_player.rect.y] != old_location:
                old_location = [local_player.rect.x, local_player.rect.y]
                send_queue.put(((1, local_player.rect.x / block_size, local_player.rect.y / block_size), SERVERADDRESS))

            # Sets the section of the world player can currently view
            displaying_world = world[offset_clip.x:offset_clip.x + size[0] // block_size + 5,
                               offset_clip.y:offset_clip.y + size[1] // block_size + 5]

            # Update cost = number of unloaded blocks on screen
            update_cost = displaying_world.flatten()
            update_cost = np.count_nonzero(update_cost == -1)

            # If there are unloaded blocks, request for chucks to be sent
            if update_cost > 0 and on_tick and (offset_clip.x, offset_clip.y) not in render_request:
                send_queue.put([[2, offset_clip.x, offset_clip.y, size, block_size], SERVERADDRESS])
                render_request.add((offset_clip.x, offset_clip.y))
            # ===================Decode Message======================

            try:
                # Message from server
                server_message = message_queue.get_nowait()
                command, message = server_message[0], server_message[1:]

                # Update remote player location
                if command == 1:
                    remote_username, current_x, current_y, tp = message

                    # If player's location has been update (For teleportation)
                    if remote_username == username:
                        if tp:
                            x_offset, y_offset = int(current_x * block_size), int(current_y * block_size)
                            local_player.rect.x, local_player.rect.y = x_offset + size[0] // 2 + block_size // 2, y_offset + size[1] // 2 + block_size // 2

                            if hotbar_items[hotbar_slot][0] != 0:
                                select_texture = item_lib[hotbar_items[hotbar_slot][0]][1]
                            else:
                                select_texture = None

                            local_player.update(surf, x_offset, y_offset, fly, current_gui, block_clip, world, block_size, block_properties, select_texture)

                    # Modify remote player object
                    elif remote_username in remote_players:
                        remote_players[remote_username].calculate_velocity(
                            (int(current_x * block_size), int(current_y * block_size)), tick_per_frame)

                    # Create remote player object
                    else:
                        remote_players[remote_username] = player.RemotePlayer(remote_username,
                                                                              int(current_x * block_size),
                                                                              int(current_y * block_size),
                                                                              (2 * block_size - 1 - 1) // 4,
                                                                              2 * block_size - 1 - 1)

                # Chunks
                elif command == 2:

                    # Chunk location + Contents
                    chunk_position_x, chunk_position_y, world_chunk = message

                    # Updates local copy of world
                    world[chunk_position_x - 5:chunk_position_x + size[0] // block_size + 5,
                    chunk_position_y - 5:chunk_position_y + size[1] // block_size + 5] = np.array(world_chunk,
                                                                                                  copy=True)

                    # Remove chunk from list of requested chunks
                    if (chunk_position_x, chunk_position_y) in render_request:
                        render_request.remove((chunk_position_x, chunk_position_y))

                # Break block
                elif command == 3:
                    pos_x, pos_y = message
                    world[pos_x, pos_y] = 0

                    if (pos_x, pos_y) in block_request:
                        block_request.remove((pos_x, pos_y))

                # Place block
                elif command == 4:
                    pos_x, pos_y, block = message
                    world[pos_x, pos_y] = block

                    if (pos_x, pos_y) in block_request:
                        block_request.remove((pos_x, pos_y))

                # Inventory updates
                elif command == 6:
                    slot, meta_data = message
                    hotbar_items[slot] = meta_data[:]

                elif command == 7:
                    slot, meta_data = message
                    inventory_items[slot] = meta_data[:]

                # Interactive block updates
                elif command == 8:
                    if message[0] != "err":
                        storage_type, storage = message

                        if storage_type == 'chest':
                            current_chest = storage
                        elif storage_type == 'furnace':
                            current_furnace = storage

                # Delete remote player
                elif command == 9:
                    remote_username = message[0]

                    del remote_players[remote_username]

                # Chat
                elif command == 10:
                    chat_list.append(message[0])

                # Get kicked from game
                elif command == 11:
                    quit_game()

                    if message[0][:9] == 'RAHDEATH:':
                        return 'death', message[0][9:]

                    else:
                        return 'information', message[0], 'menu'

                elif command == 12:
                    # Health
                    health = message[0]

                elif command == 13:
                    # Hunger
                    hunger = message[0]

                elif command == 14:

                    # Complete sync
                    # #Incase something goes terribly wrong, server and resync all player parameters
                    world_size_x, world_size_y, player_x_, player_y_, hotbar_items, inventory_items, r_players, health, hunger = message[0:]

                    # Updates player location
                    player_x = int(float(player_x_) * block_size)
                    player_y = int(float(player_y_) * block_size)

                    # Updates world
                    world = np.array([[-1] * (world_size_y + 40) for _ in range(world_size_x)])

                    # Recreates player object
                    local_player = player.Player(player_x, player_y, (2 * block_size - 1 - 1) // 4, 2 * block_size - 1 - 1,
                                                 block_size, (K_a, K_d, K_w, K_s, K_SPACE))

                    # Resets camera location
                    x_offset = local_player.rect.x - size[0] // 2 + block_size // 2
                    y_offset = local_player.rect.y - size[1] // 2 + block_size // 2

                    # Resets remote players
                    remote_players = {}

                    # Requests for world again
                    send_queue.put(
                        [[2, x_offset // block_size, y_offset // block_size, size, block_size], SERVERADDRESS])

                    # Waiting for server to respond with world
                    while True:
                        world_msg = message_queue.get()
                        rah.rahprint(world_msg)
                        if world_msg[0] == 2:
                            break

                    # Updates local copy of world
                    world[world_msg[1] - 5:world_msg[1] + size[0] // block_size + 5,
                    world_msg[2] - 5:world_msg[2] + size[1] // block_size + 5] = np.array(world_msg[3], copy=True)

                    # Creates remote player objects
                    for Rp in r_players:
                        remote_players[Rp] = player.RemotePlayer(Rp, r_players[Rp][0], r_players[Rp][1],
                                                                 (2 * block_size - 1 - 1) // 4, 2 * block_size - 1 - 1)

                    # Broadcasts ping to refesh session
                    for repeat in range(5):
                        send_queue.put(([(101, username), SERVERADDRESS]))

                # Inventory update
                elif command == 15:
                    hotbar_items = message[0]
                    inventory_items = message[1]

                # Game tick sync
                elif command == 100:
                    send_time, tick = message

                    tick_offset = (round(ti.time(), 3) - send_time) * 20

                    sky_tick = tick_offset + tick

                    for repeat in range(3):
                        send_queue.put(([(101, username), SERVERADDRESS]))

            except:
                # Nothing in queue
                pass

            # Adding Sky
            # =======================================================
            if on_tick:
                if not sky_diming:
                    sky_tick += 1
                else:
                    sky_tick -= 1

            # Sky changes direction (Sun rise or sun set)
            if sky_tick > 12000:
                sky_diming = True
                sky_tick = sky_tick - (sky_tick - 12000)
            elif sky_tick < 0:
                sky_diming = False
                sky_tick = sky_tick + abs(sky_tick)

                rah.rahprint("Reset")

            # Renders sky
            for y in range(size[1]):
                r = min(max(int(((y_offset // block_size) / world_size_y) * 20 - int(255 * sky_tick / 24000)), 0), 255)
                g = min(max(int(((y_offset // block_size) / world_size_y) * 200 - int(255 * sky_tick / 24000)), 0), 255)
                b = min(max(int(((y_offset // block_size) / world_size_y) * 300 - int(255 * sky_tick / 24000)), 0), 255)

                draw.line(surf, (r, g, b), (0, y), (size[0], y), 1)

            # Draws stars during the day time
            if sky_tick < 6000 or sky_tick > 0:
                for star in star_list:
                    draw.circle(surf, (255, 255, 255), (int(star[0]), star[1]), randint(1, 2))

                    star[0] += 0.05

                    if star[0] > size[0]:
                        star[0] = 0

            # Draws sun and moon
            surf.blit(sun, (int(5600 - 4800 * (sky_tick % 24000) / 24000), max(y_offset // 50 + 50, -200)))
            surf.blit(moon, (int(2800 - 4800 * (sky_tick % 24000) / 24000), max(y_offset // 50 + 50, -200)))

            draw.rect(surf, (0, 0, 0), (0, (100 * block_size) - y_offset, size[0], size[1]))

            # Cave tiles
            bg_tile = Surface((block_size, block_size))
            bg_tile.blit(block_properties[9]['texture'], (0, 0))
            bg_tile.set_alpha(200)

            for x in range(0, size[0], block_size):
                for y in range(0, 70 * block_size, block_size):
                    surf.blit(bg_tile, (x, y + (100 * block_size) - y_offset))

            # Render World
            # =======================================================
            try:
                render_world()
            except:
                pass

            # Block player currently is holding
            if hotbar_items[hotbar_slot][0] != 0:
                select_texture = item_lib[hotbar_items[hotbar_slot][0]][1]
            else:
                select_texture = None

            # Updates player object
            local_player.update(surf, x_offset, y_offset, fly, current_gui, block_clip, world, block_size,
                                block_properties, select_texture)

            # Tells server if fall damage occured
            if local_player.fall_distance > 10:
                # Reduces health
                health -= (local_player.fall_distance // 10)

                # Sends damage to server
                send_queue.put(((12, health), SERVERADDRESS))

                # Resets fall distance
                local_player.fall_distance = 0

                # Plays fall sound
                rah.load_sound(damage_list)
                rah.load_sound(['sound/random/classic_hurt.ogg'])

            # Gets block below player to play block sound
            under_block = ((x_offset + size[0] // 2) // block_size, (y_offset + size[1] // 2) // block_size)

            # Plays sound of block under player
            if world[under_block] > 0 and block_step != under_block:
                rah.load_sound(sound['step'][block_properties[world[under_block]]['sound']])

                block_step = under_block

            # ==========================Mouse Interaction=================================
            mb = mouse.get_pressed()
            mx, my = mouse.get_pos()

            # Block mouse is currently over
            hover_x, hover_y = ((mx + x_offset) // block_size, (my + y_offset) // block_size)

            # Cord of snapped block
            block_clip_cord = (block_clip[0] // block_size, block_clip[1] // block_size)

            # If no GUI is being used
            if not current_gui:

                # Left click release
                if mb[0] == 0:
                    current_breaking = []
                    breaking_block = False

                # Left click down
                elif mb[0] == 1:

                    # Makes block break request
                    if not breaking_block and world[hover_x, hover_y] > 0 and (
                            hover_x, hover_y) not in block_request and hypot(hover_x - block_clip_cord[0],
                                                                             hover_y - block_clip_cord[1]) <= reach:

                        # Flags block breaking
                        breaking_block = True

                        # Gets block breaking
                        current_breaking = [world[hover_x, hover_y], hover_x, hover_y, 1]

                        # Breaks block if enough time
                        if current_breaking[3] >= block_properties[current_breaking[0]]['hardness']:
                            block_broken = True

                    # If increments the block breaking
                    elif breaking_block and hypot(hover_x - block_clip_cord[0], hover_y - block_clip_cord[1]) <= reach:

                        # If mouse is over the block being broken
                        if hover_x == current_breaking[1] and hover_y == current_breaking[2]:

                            # If the tool selected is the best one for the block
                            if hotbar_items[hotbar_slot][0] in tool_properties:

                                # Get current tool
                                current_tool = hotbar_items[hotbar_slot][0]

                                # Compares tool to ideal tool for block
                                if tool_properties[current_tool]['type'] == \
                                        block_properties[world[hover_x, hover_y]]['tool']:

                                    # Gives bonus if correct tool
                                    current_breaking[3] += tool_properties[current_tool]['bonus']
                                else:
                                    # Gives tool standard speed
                                    current_breaking[3] += tool_properties[current_tool]['speed']
                            else:
                                # Standard slow breaking
                                current_breaking[3] += 1

                            # If block is broken
                            if current_breaking[3] >= block_properties[current_breaking[0]]['hardness']:
                                block_broken = True

                            # Play punching sound
                            rah.load_sound(sound['step'][block_properties[world[hover_x, hover_y]]['sound']])

                        else:
                            # If block is released before it's broken
                            breaking_block = False
                            current_breaking = []

                    # When block is broken
                    if block_broken:

                        # Play destroy sound
                        rah.load_sound(sound['dig'][block_properties[world[hover_x, hover_y]]['sound']])

                        # Updates tool durability
                        if hotbar_items[hotbar_slot][0] in tool_properties:
                            if len(hotbar_items[hotbar_slot]) == 2:
                                hotbar_items[hotbar_slot].append(
                                    tool_properties[hotbar_items[hotbar_slot][0]]['durability'])
                            else:
                                # Increments durability
                                hotbar_items[hotbar_slot][2] -= 1

                                # Removes item if it is dead
                                if hotbar_items[hotbar_slot][2] == 0:
                                    hotbar_items[hotbar_slot] = [0, 0]

                        # If the block requires a certain block for an item drop
                        if block_properties[world[hover_x, hover_y]]['tool-required']:

                            # If item in hand is a tool
                            if hotbar_items[hotbar_slot][0] in tool_properties:
                                current_tool = hotbar_items[hotbar_slot][0]

                                # If tool type matches required
                                if tool_properties[current_tool]['type'] == block_properties[world[hover_x, hover_y]][
                                    'tool']:
                                    # Add block to inventory
                                    inventory_items, hotbar_items = pickup_item(inventory_items, hotbar_items,
                                                                                block_properties[
                                                                                    world[hover_x, hover_y]]['drop'],
                                                                                item_lib)
                        else:
                            # Add block to inventory
                            inventory_items, hotbar_items = pickup_item(inventory_items, hotbar_items,
                                                                        block_properties[world[hover_x, hover_y]][
                                                                            'drop'], item_lib)

                        # Indicates inventory has been updated to sync with server
                        inventory_updated = True

                        # Request to break block from server
                        block_request.add((hover_x, hover_y))
                        send_queue.put(((3, hover_x, hover_y), SERVERADDRESS))

                        # Resets values
                        current_breaking = []
                        breaking_block = False

                # If left click and in range of mouse
                if mb[2] == 1 and hypot(hover_x - block_clip_cord[0], hover_y - block_clip_cord[1]) <= reach:

                    # Select crafting table
                    if world[hover_x, hover_y] == 10 and current_gui == '':
                        crafting = True
                        current_gui = 'C'

                    # Select chest
                    elif world[hover_x, hover_y] == 17 and current_gui == '':
                        using_chest = True
                        current_gui = 'Ch'
                        chest_location = [hover_x, hover_y]
                        send_queue.put(((7, 'chest', hover_x, hover_y, 1), SERVERADDRESS))

                    # Select furnace
                    elif world[hover_x, hover_y] == 18 and current_gui == '':
                        using_furnace = True
                        current_gui = 'F'
                        furnace_location = [hover_x, hover_y]

                        # Tells server furnace is being interacted with
                        send_queue.put(((7, 'furnace', hover_x, hover_y, 1), SERVERADDRESS))


                    # Place block
                    elif world[hover_x, hover_y] == 0 and sum(get_neighbours(hover_x, hover_y)) > 0 and (
                            hover_x, hover_y) not in block_request and on_tick and hotbar_items[hotbar_slot][1] != 0 and hotbar_items[hotbar_slot][
                        0] in block_properties and hotbar_items[hotbar_slot][1] > 0:

                        # Asks server to place block
                        block_request.add((hover_x, hover_y))
                        send_queue.put(
                            ((4, hover_x, hover_y, hotbar_items[hotbar_slot][0], hotbar_slot), SERVERADDRESS))

                        # Block sound
                        hover_sound = block_properties[hotbar_items[hotbar_slot][0]]
                        if hover_sound['sound'] != 'nothing':
                            rah.load_sound(sound['dig'][hover_sound['sound']])

                # Middle click to get block
                if debug and mb[1] == 1 and hypot(hover_x - block_clip_cord[0], hover_y - block_clip_cord[1]) <= reach:
                    hotbar_items[hotbar_slot] = [world[hover_x, hover_y], 1]

                # Highlight cursor if in reach
                if hypot(hover_x - block_clip_cord[0], hover_y - block_clip_cord[1]) <= reach:
                    surf.blit(highlight_good, ((mx + x_offset) // block_size * block_size - x_offset,
                                               (my + y_offset) // block_size * block_size - y_offset))
                else:
                    surf.blit(highlight_bad, ((mx + x_offset) // block_size * block_size - x_offset,
                                              (my + y_offset) // block_size * block_size - y_offset))

            # Update remote players
            for remote in remote_players:
                remote_players[remote].update(surf, x_offset, y_offset)

            # ====================Inventory/hotbar========================

            # Size of heat icon
            HEART_SIZE = 15

            # Renders hearts
            for heart_index in range(0, 20, 2):

                # Get heart location based on heart #
                heart_x = heart_index // 2 * (HEART_SIZE + 1)
                surf.blit(transform.scale(health_texture['none'], (HEART_SIZE + 1, HEART_SIZE + 1)), (hotbar_rect[0] + heart_x - 1, hotbar_rect[1] - HEART_SIZE - 6))

                if heart_index < health - 2:

                    # Empty heart
                    surf.blit(transform.scale(health_texture['full'], (HEART_SIZE, HEART_SIZE)),
                              (hotbar_rect[0] + heart_x, hotbar_rect[1] - HEART_SIZE - 5))

                # Atleast one heart
                elif heart_index <= health - 1:

                    # Decides full or half heart
                    if (health - heart_index) % 2 == 0:
                        heart_texture = health_texture['full']
                    else:
                        heart_texture = health_texture['half']

                    # Blits the heart
                    surf.blit(transform.scale(heart_texture, (HEART_SIZE, HEART_SIZE)),
                              (hotbar_rect[0] + heart_x, hotbar_rect[1] - HEART_SIZE - 5))

            '''
            HUNGER_SIZE = 15

            for hunger_index in range(0, 20, 2):

                hunger_x = hunger_index // 2 * (HUNGER_SIZE + 1)
                surf.blit(transform.scale(hunger_texture['none'], (HUNGER_SIZE + 1, HUNGER_SIZE + 1)),
                          (hotbar_rect[0] + hotbar.get_width() - 10 * HUNGER_SIZE + hunger_x - 11, hotbar_rect[1] - HUNGER_SIZE - 6))

                if hunger_index < hunger - 2:
                    surf.blit(transform.scale(hunger_texture['full'], (HUNGER_SIZE, HUNGER_SIZE)),
                              (hotbar_rect[0] + hotbar.get_width() - 10 * HUNGER_SIZE + hunger_x - 10, hotbar_rect[1] - HUNGER_SIZE - 5))

                elif hunger_index <= hunger - 1:

                    if (hunger - hunger_index) % 2 == 0:
                        food_texture = hunger_texture['full']
                    else:
                        food_texture = hunger_texture['half']

                    surf.blit(transform.scale(food_texture, (HUNGER_SIZE, HUNGER_SIZE)),
                              (hotbar_rect[0] + hotbar.get_width() - 10 * HUNGER_SIZE + hunger_x - 10, hotbar_rect[1] - HUNGER_SIZE - 5))
            '''

            # Renders hotbar
            render_hotbar(hotbar_slot)

            # ===================Pausing====================================
            if paused:

                # Background tint
                surf.blit(tint, (0, 0))

                # Caption
                text_surface = rah.text('Game Paused', 20)
                surf.blit(text_surface, (size[0] // 2 - text_surface.get_width() // 2, 50))

                # Creates menu class
                nav_update = pause_menu.update(surf, release, mx, my, mb)

                # Updates if button is clicked
                if nav_update:

                    # If back button is clicked
                    if nav_update == 'unpause':
                        paused = False
                    elif nav_update == 'menu':
                        quit_game()
                        return 'menu'
                    else:
                        return nav_update

            # Chest UI
            elif using_chest:

                # Update chests
                surf.blit(tint, (0, 0))
                changed = chest_object.update(surf, mx, my, mb, l_click, r_click, inventory_items, hotbar_items, current_chest, item_lib)

                if changed != [0, 0]:
                    send_queue.put((changed + [chest_location[0], chest_location[1]], SERVERADDRESS))

            # Furnace UI
            elif using_furnace:

                furnace_old = deepcopy(current_furnace)
                surf.blit(tint, (0, 0))

                # Updates furnace
                furnace_object.update(surf, mx, my, mb, l_click, r_click, inventory_items, hotbar_items, current_furnace, item_lib)

                # Syncs furnace with server
                if current_furnace != [] and current_furnace != furnace_old:
                    send_queue.put(((8, 'furnace', furnace_location[0], furnace_location[1], current_furnace), SERVERADDRESS))

            # Inventory
            elif inventory_visible:
                surf.blit(tint, (0, 0))

                # Updates inventory object
                inventory_object.update(surf, mx, my, mb, l_click, r_click, inventory_items, hotbar_items, item_lib)

            # Crafting
            elif crafting:
                surf.blit(tint, (0, 0))

                # Updates crafting object
                crafting_object.update(surf, mx, my, mb, l_click, r_click, inventory_items, hotbar_items, item_lib)

            # Tab player menu
            if not paused:
                if key.get_pressed()[K_TAB]:

                    # Formats text in list
                    players = ['RahCraft',
                               '---------',
                               username] + [player for player in remote_players]

                    # Tab menu tint
                    tab_back = Surface((200, len(players) * 30 + 10), SRCALPHA)
                    tab_back.fill(Color(75, 75, 75, 150))
                    surf.blit(tab_back, (size[0] // 2 - 100, 40))

                    # Draws text
                    for y in range(0, len(players)):
                        about_text = normal_font.render(players[y], True, (255, 255, 255))
                        surf.blit(about_text, (size[0] // 2 - about_text.get_width() // 2, 50 + y * 20))

            # Clears chat if it goes off screen
            while len(chat_list) * text_height > (5 * size[1]) // 8:
                del chat_list[0]

            # Blits chat twxt
            for line in range(len(chat_list)):
                surf.blit(rah.text(chat_list[line], 10), (20, line * (text_height + 3)))

            # Updates chatbox object
            if chat_enable:
                chat_content = chat.update(pass_event)
                chat.draw(surf, '')

            # Debug menu
            if debug:
                # Debug stats
                debug_list = ["%s" % build,
                              "FPS: %i" % round(clock.get_fps(), 2),
                              "X:%i Y:%i" % (offset_clip.x, y_offset // block_size),
                              "Block Size: %i" % block_size,
                              "Hotbar Slot: %i" % hotbar_slot,
                              "Block Selected: %s" % str(item_lib[hotbar_items[hotbar_slot][0]][0]),
                              "Mouse Pos: %i, %i" % ((mx + x_offset) // block_size, (my + y_offset) // block_size),
                              "Update Cost: %i" % update_cost,
                              "Time: %s" % sky_tick,
                              "Token: %s" % token[0:10]]

                # Blits the stats
                for y in range(len(debug_list)):
                    about_text = rah.text(debug_list[y], 15)
                    surf.blit(about_text, (size[0] - about_text.get_width() - 10, 10 + y * 20))

            # Lock frame rate and update screen
            clock.tick(120)
            display.set_caption("RahCraft // FPS - {0}".format(clock.get_fps()))
            display.update()

    except:
        # If an error occurs, return error and quit game
        quit_game()
        return 'crash', traceback.format_exc(), 'menu'
