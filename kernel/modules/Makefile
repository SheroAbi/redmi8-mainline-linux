# make KDIR=<configured 7.1.3-msm89x7-olive-r7 tree>
#
# LOCALVERSION= keeps kbuild from appending "+" for a dirty tree; the
# "-msm89x7-olive-r7" suffix comes from CONFIG_LOCALVERSION in the config.
KDIR ?= /lib/modules/$(shell uname -r)/build
KMAKE = $(MAKE) -C $(KDIR) M=$(CURDIR) ARCH=arm64 LLVM=1 LOCALVERSION=

all:
	$(KMAKE) KBUILD_MODPOST_WARN=1 modules

clean:
	$(KMAKE) clean

.PHONY: all clean
