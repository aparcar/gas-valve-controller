# Description: Action executed on boot (bind) and with the system on the fly

LINKS=""
LINKS="$LINKS 1-1.3.3:1.0#relay"
LINKS="$LINKS 1-1.3.1.4:1.0#mpv1"
LINKS="$LINKS 1-1.3.1.1:1.0#mpv2"
LINKS="$LINKS 1-1.3.1.2:1.0#mpv3"
LINKS="$LINKS 1-1.3.2:1.0#analyzer"


for LINK in $LINKS; do
        LINK_PATH="$(echo $LINK | cut -d '#' -f 1)"
        LINK_ALIAS="$(echo $LINK | cut -d '#' -f 2)"
        if [ "$DEVICENAME" = "$LINK_PATH" ]; then
                logger -t symlinks "Found device $LINK_PATH -> $LINK_ALIAS"
                if [ "${ACTION}" = "add" ] ; then
                        DEVTTY="$(ls /sys/${DEVPATH}/ | grep tty)"
                        ln -s "/dev/$DEVTTY" "/dev/$LINK_ALIAS"
                        logger -t symlinks "Symlink /dev/$LINK_ALIAS added"
                fi

                if [ "${ACTION}" = "remove" ]; then
                        rm "/dev/$LINK_ALIAS"
                        logger -t symlinks "Symlink /dev/$LINK_ALIAS removed"
                fi
        fi
done

