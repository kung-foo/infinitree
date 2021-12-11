BASE_DIR := /media/$(USER)

ifneq ($(wildcard $(BASE_DIR)/INFINITREE/*),)
TARGET := $(BASE_DIR)/INFINITREE
else
TARGET := $(BASE_DIR)/CIRCUITPY
endif

CPY_BUNDLE	:= 20211125
LIB_ROOT 	:= adafruit-circuitpython-bundle-7.x-mpy-$(CPY_BUNDLE)/lib
CPY_LIBS 	:= 	$(LIB_ROOT)/neopixel.mpy \
				$(LIB_ROOT)/adafruit_datetime.mpy

COMMUNITY_BUNDLE	:= 20211127
COMMUNITY_ROOT 		:= circuitpython-community-bundle-7.x-mpy-$(COMMUNITY_BUNDLE)/lib

CPY_RUNTIME := 7.1.0-beta.1
# CPY_RUNTIME := https://adafruit-circuit-python.s3.amazonaws.com/bin/feather_m4_express/en_US/adafruit-circuitpython-feather_m4_express-en_US-7.1.0-beta.1.uf2

deploy:
	cp code.py boot.py $(TARGET)

install_libs:
	-$(eval TMPDIR := $(shell mktemp -d))

	curl -qsL -o $(TMPDIR)/bundle.zip  https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/download/$(CPY_BUNDLE)/adafruit-circuitpython-bundle-7.x-mpy-$(CPY_BUNDLE).zip
	unzip -j -o $(TMPDIR)/bundle.zip -d $(TARGET)/lib $(CPY_LIBS)

	curl -qsL -o $(TMPDIR)/bundle.zip  https://github.com/adafruit/CircuitPython_Community_Bundle/releases/download/$(COMMUNITY_BUNDLE)/circuitpython-community-bundle-7.x-mpy-$(COMMUNITY_BUNDLE).zip
	unzip -j -o $(TMPDIR)/bundle.zip -d $(TARGET)/lib/asynccp/ $(COMMUNITY_ROOT)/asynccp/*

	-rm -rf $(TMPDIR)

watch:
	while inotifywait -e close_write code.py; do \
		make deploy; \
	done