# Build the libnova adapter
# Compiles required libnova sources from the vendored submodule and links
# the adapter against them.

LIBNOVA_SRC_DIR := vendor/libnova/src

# Only the source files we actually need.
LIBNOVA_SRCS := \
	$(LIBNOVA_SRC_DIR)/precession.c \
	$(LIBNOVA_SRC_DIR)/nutation.c \
	$(LIBNOVA_SRC_DIR)/sidereal_time.c \
	$(LIBNOVA_SRC_DIR)/utility.c \
	$(LIBNOVA_SRC_DIR)/dynamical_time.c \
	$(LIBNOVA_SRC_DIR)/transform.c \
	$(LIBNOVA_SRC_DIR)/solar.c \
	$(LIBNOVA_SRC_DIR)/earth.c \
	$(LIBNOVA_SRC_DIR)/vsop87.c \
	$(LIBNOVA_SRC_DIR)/mercury.c \
	$(LIBNOVA_SRC_DIR)/venus.c \
	$(LIBNOVA_SRC_DIR)/mars.c \
	$(LIBNOVA_SRC_DIR)/jupiter.c \
	$(LIBNOVA_SRC_DIR)/saturn.c \
	$(LIBNOVA_SRC_DIR)/uranus.c \
	$(LIBNOVA_SRC_DIR)/neptune.c \
	$(LIBNOVA_SRC_DIR)/lunar.c \
	$(LIBNOVA_SRC_DIR)/elliptic_motion.c \
	$(LIBNOVA_SRC_DIR)/julian_day.c \
	$(LIBNOVA_SRC_DIR)/rise_set.c \
	$(LIBNOVA_SRC_DIR)/apparent_position.c \
	$(LIBNOVA_SRC_DIR)/aberration.c \
	$(LIBNOVA_SRC_DIR)/refraction.c \
	$(LIBNOVA_SRC_DIR)/proper_motion.c

# ELP 2000-82B lunar data tables (required by lunar.c)
ELP_SRCS := $(wildcard $(LIBNOVA_SRC_DIR)/elp/*.c)
ELP_OBJS := $(patsubst $(LIBNOVA_SRC_DIR)/elp/%.c, build/libnova/elp/%.o, $(ELP_SRCS))

LIBNOVA_OBJS := $(patsubst $(LIBNOVA_SRC_DIR)/%.c, build/libnova/%.o, $(LIBNOVA_SRCS))
ADAPTER_SRCS := $(sort $(wildcard src/*.c))
ADAPTER_OBJS := $(patsubst src/%.c, build/src/%.o, $(ADAPTER_SRCS))

CC       := gcc
CFLAGS   := -O3 -Wall -std=c11 -D_GNU_SOURCE -I. -Isrc -I$(LIBNOVA_SRC_DIR) \
             -Wno-unused-function -Wno-unused-variable -Wno-sign-compare \
             -Wno-misleading-indentation -Wno-implicit-function-declaration \
             -Wno-int-conversion
LDFLAGS  := -lm

TARGET   := build/libnova_adapter

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(ADAPTER_OBJS) $(LIBNOVA_OBJS) $(ELP_OBJS)
	$(CC) -o $@ $^ $(LDFLAGS)

build/src/%.o: src/%.c src/common.h | build/src
	$(CC) $(CFLAGS) -c -o $@ $<

build/libnova/%.o: $(LIBNOVA_SRC_DIR)/%.c | build/libnova
	$(CC) $(CFLAGS) -c -o $@ $<

build/libnova/elp/%.o: $(LIBNOVA_SRC_DIR)/elp/%.c | build/libnova/elp
	$(CC) $(CFLAGS) -c -o $@ $<

build:
	mkdir -p build

build/src:
	mkdir -p build/src

build/libnova:
	mkdir -p build/libnova

build/libnova/elp:
	mkdir -p build/libnova/elp

clean:
	rm -rf build
