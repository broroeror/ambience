import QtQuick
import QtQuick.Controls.Basic

MenuItem {
    id: item
    implicitHeight: 38
    contentItem: Label {
        text: item.text
        leftPadding: 10
        color: item.enabled ? Theme.text : Theme.muted
        font.weight: Font.DemiBold
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 8
        color: item.highlighted ? Theme.lineStrong : "transparent"
    }
}
