# Build the ERFA adapter
# Compiles ERFA from the vendored submodule and links the adapter against it.

ERFA_SRC_DIR := vendor/erfa/src
ADAPTER_SRC_DIR := src
ERFA_SRCS    := $(filter-out $(ERFA_SRC_DIR)/t_%, $(wildcard $(ERFA_SRC_DIR)/*.c))
ERFA_OBJS    := $(patsubst $(ERFA_SRC_DIR)/%.c, build/erfa/%.o, $(ERFA_SRCS))
ADAPTER_SRCS := $(wildcard $(ADAPTER_SRC_DIR)/*.c)
ADAPTER_OBJS := $(patsubst $(ADAPTER_SRC_DIR)/%.c, build/adapter/%.o, $(ADAPTER_SRCS))

CC       := gcc
CFLAGS   := -O3 -Wall -std=c11 -I$(ERFA_SRC_DIR) -I$(ADAPTER_SRC_DIR) -Wno-return-type \
             -DPACKAGE_VERSION=\"2.0.1\" -DPACKAGE_VERSION_MAJOR=2 \
             -DPACKAGE_VERSION_MINOR=0 -DPACKAGE_VERSION_MICRO=1 \
             -DSOFA_VERSION=\"20231011\"
LDFLAGS  := -lm

TARGET   := build/erfa_adapter

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(ADAPTER_OBJS) $(ERFA_OBJS)
	$(CC) -o $@ $^ $(LDFLAGS)

build/adapter/%.o: $(ADAPTER_SRC_DIR)/%.c | build/adapter
	$(CC) $(CFLAGS) -c -o $@ $<

build/erfa/%.o: $(ERFA_SRC_DIR)/%.c | build/erfa
	$(CC) $(CFLAGS) -c -o $@ $<

build:
	mkdir -p build

build/adapter:
	mkdir -p build/adapter

build/erfa:
	mkdir -p build/erfa

clean:
	rm -rf build
