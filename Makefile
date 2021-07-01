# SPDX-License-Identifier: GPL-2.0

include $(TOPDIR)/rules.mk

PKG_NAME:=valve-controller
PKG_VERSION:=$(COMMITCOUNT)
PKG_LICENSE:=GPL-2.0

include $(INCLUDE_DIR)/package.mk

define Package/valve-controller
  SECTION:=utils
  CATEGORY:=Base system
  TITLE:=Common files neede by attendedsysupgrade packages
  MAINTAINER:=Paul Spooren <mail@aparcar.org>
  DEPENDS:=+rpcd +rpcd-mod-rpcsys
  PKGARCH:=all
endef

define Package/valve-controller/description
endef

define Build/Compile
endef

define Build/Configure
endef

define Package/valve-controller/install
	$(INSTALL_DIR) $(1)/etc/init.d/
	$(INSTALL_BIN) ./valve-controller.init $(1)/etc/init.d/valve-controller

	$(INSTALL_DIR) $(1)/usr/bin/
	$(INSTALL_BIN) ./valve-controller.py $(1)/usr/bin/valve-controller

	$(INSTALL_DIR) $(1)/www/cgi-bin/
	$(INSTALL_BIN) ./index.html $(1)/www/
	$(INSTALL_BIN) ./valve-controller.js $(1)/www/
	$(INSTALL_BIN) ./valve-cgi $(1)/www/cgi-bin/

	$(INSTALL_DIR) $(1)/etc/hotplug.d/usb/
	$(INSTALL_BIN) ./hotplug.sh $(1)/etc/hotplug.d/usb/


endef

$(eval $(call BuildPackage,valve-controller))

