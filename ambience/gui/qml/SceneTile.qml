import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// One scene: your own photo if you set one, else its glow. Amber border = active; a small
// wave marks scenes that can play dynamically.
Rectangle {
    id: tile
    required property var item          // filled from the model's `item` role
    property bool showGroup: false
    signal clicked()
    signal menuRequested()

    width: 150; height: 112
    radius: 14
    color: Theme.surface
    border.width: 2
    border.color: tile.item.active ? Theme.accent
                : tile.item.selected ? Theme.text
                : hover.hovered ? Theme.lineStrong : Theme.line
    Behavior on border.color { ColorAnimation { duration: 150 } }

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { acceptedButtons: Qt.LeftButton; onTapped: tile.clicked() }
    TapHandler { acceptedButtons: Qt.RightButton; onTapped: tile.menuRequested() }
    TapHandler { acceptedButtons: Qt.LeftButton; onLongPressed: tile.menuRequested() }

    Accessible.role: Accessible.Button
    Accessible.name: tile.item.name || ""

    Glow {
        id: glow
        x: 2; y: 2; width: parent.width - 4; height: 70
        topRadius: 12
        visible: !tile.item.photo
        colors: tile.item.glow || []
    }

    Image {   // your photo, cropped to fill, rounded via a mask
        id: photo
        x: 2; y: 2; width: parent.width - 4; height: 70
        visible: false
        source: tile.item.photo || ""
        fillMode: Image.PreserveAspectCrop
        sourceSize.width: 300
        asynchronous: true
    }
    Item {
        id: mask
        x: 2; y: 2; width: photo.width; height: photo.height
        visible: false
        layer.enabled: true
        Rectangle { anchors.fill: parent; topLeftRadius: 12; topRightRadius: 12; color: "black" }
    }
    MultiEffect {
        x: 2; y: 2; width: photo.width; height: photo.height
        visible: !!tile.item.photo
        source: photo
        maskEnabled: true
        maskSource: mask
    }

    Label {
        x: 12; y: 78; width: parent.width - 24 - (wave.visible ? 18 : 0)
        text: tile.item.name || ""
        color: Theme.text; font.weight: Font.Bold; elide: Text.ElideRight
    }
    Label {
        id: wave
        visible: !!tile.item.dynamic
        anchors.right: parent.right; anchors.rightMargin: 10; y: 76
        text: "∿"; color: tile.item.playing === "dynamic_palette" ? Theme.accent : Theme.muted
        font.pixelSize: 18; font.weight: Font.Bold
        Accessible.name: "Can play dynamically"
    }
}
