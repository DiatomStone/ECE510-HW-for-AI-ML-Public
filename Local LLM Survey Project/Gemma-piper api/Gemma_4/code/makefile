# Output program name
TARGET = program
# Arguments
a1 ?=
a2 ?= 
#directories
SRC_DIR = src
HDR_DIR = include
OBJ_DIR = obj
ELF_DIR = build

# Compiler
CC = gcc
# Compiler flags
CFLAGS = -Wall -Wextra -std=c11 -I./include
# linker flag
LDFLAGS =  

# Source and header files
SRC = program.c
HEADERS = 
OBJ = $(SRC:$(SRC_DIR)/%.c=$(OBJ_DIR)/%.o)
# arguments: file, Threads
ARGC = $(a1) $(a2)


# Default rule: build the program
all: $(TARGET)

# How to build the final executable
$(TARGET): $(OBJ)
	#@mkdir -p $(ELF_DIR)
	$(CC) $(CFLAGS) $(OBJ) -o $(TARGET) $(LDFLAGS)

# How to build each .o file from its .c file
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c $(HEADERS)
	@mkdir -p $(OBJ_DIR)
	$(CC) $(CFLAGS) -c $< -o $@ 
	
# Run the program with sample arguments
run: $(TARGET)
	./$(TARGET) $(ARGC)

# Clean up build files
clean:
	rm -rf $(OBJ_DIR) $(ELF_DIR) *.data *.old *.o *.tmp
	
#------------perf

#------------flamegraph 

.PHONY: all clean run

