import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id: page
    signal back()
    readonly property var room: backend.room
    readonly property var light: backend.light

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Flickable {
            id: main
            Layout.fillWidth: true; Layout.fillHeight: true
            contentHeight: col.implicitHeight + 56
            clip: true
            ScrollBar.vertical: ScrollBar {}
            FastWheel { flick: main }

            ColumnLayout {
                id: col
                x: 36; y: 28; width: main.width - 72
                spacing: 24

                ColumnLayout {   // header: title row, then the room's controls on their own line
                    Layout.fillWidth: true
                    spacing: 14
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 16
                        Button {
                            id: backBtn
                            implicitWidth: 44; implicitHeight: 44
                            onClicked: page.back()
                            Accessible.name: "Back to Home"
                            contentItem: Label { text: "‹"; color: Theme.text; font.pixelSize: 26; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 22; color: backBtn.hovered ? Theme.raised : Theme.surface; border.color: Theme.lineStrong }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Label { text: page.room.name || ""; color: Theme.text; font.pixelSize: 28; font.weight: Font.ExtraBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Label { text: page.room.meta || ""; color: Theme.muted; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        Toggle {
                            liveChecked: !!page.room.on
                            onToggled: backend.setGroupOn(page.room.groupedId, checked)
                            Accessible.name: "Room power"
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 60
                        spacing: 12
                        Label { text: "Brightness"; color: Theme.muted; font.pixelSize: 13 }
                        AmberSlider {
                            Layout.fillWidth: true
                            Layout.maximumWidth: 420
                            liveValue: page.room.bri || 0
                            enabled: !!page.room.on
                            onMoved: backend.setGroupBrightness(page.room.groupedId, value)
                            Accessible.name: "Room brightness"
                        }
                        Label { text: (page.room.bri || 0) + "%"; color: Theme.text; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight }
                        Item { Layout.fillWidth: true }
                    }
                }

                Label { text: "SCENES"; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1 }
                SceneStrip {
                    Layout.fillWidth: true
                    Layout.preferredHeight: implicitHeight
                    model: backend.scenesModel
                }

                Label { text: "LIGHTS"; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1 }
                GridLayout {
                    Layout.fillWidth: true
                    columns: Math.max(1, Math.floor((main.width - 72 + 14) / (190 + 14)))
                    columnSpacing: 14; rowSpacing: 14
                    Repeater {
                        model: backend.lightsModel
                        delegate: Rectangle {
                            id: tile
                            required property var item
                            // The light's colour, eased: everything on the tile derives from it,
                            // so bulb, halo, tint and border all fade together.
                            property color lit: tile.item.hex
                            Behavior on lit { ColorAnimation { duration: Theme.fadeMs; easing.type: Easing.InOutQuad } }
                            Layout.fillWidth: true
                            Layout.preferredHeight: 132
                            radius: 16
                            color: Qt.tint(Theme.surface, Qt.rgba(tile.lit.r, tile.lit.g, tile.lit.b, 0.22))
                            border.width: 2
                            border.color: tile.item.selected ? "white" : Qt.tint(Theme.line, Qt.rgba(tile.lit.r, tile.lit.g, tile.lit.b, 0.4))
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: backend.selectLight(tile.item.id) }
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 16
                                spacing: 10
                                RowLayout {
                                    Layout.fillWidth: true
                                    Rectangle {   // the bulb
                                        width: 34; height: 34; radius: 17
                                        color: tile.lit
                                        Rectangle {  // soft halo
                                            opacity: tile.item.on ? 1 : 0
                                            Behavior on opacity { NumberAnimation { duration: Theme.fadeMs } }
                                            anchors.centerIn: parent; z: -1
                                            width: 54; height: 54; radius: 27
                                            color: Qt.rgba(tile.lit.r, tile.lit.g, tile.lit.b, 0.25)
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Toggle {
                                        liveChecked: tile.item.on
                                        onToggled: backend.setLightOn(tile.item.id, checked)
                                        Accessible.name: tile.item.name + " power"
                                    }
                                }
                                Label { text: tile.item.name; color: Theme.text; font.pixelSize: 15; font.weight: Font.ExtraBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: tile.item.on ? tile.item.bri + "% · " + tile.item.kind : "Off · " + tile.item.kind; color: Theme.textSoft; font.pixelSize: 12 }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {   // selected-light panel
            Layout.preferredWidth: Math.min(340, Math.max(290, page.width * 0.34)); Layout.fillHeight: true
            color: Theme.sidebar
            Rectangle { width: 1; height: parent.height; color: Theme.line }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 24; anchors.topMargin: 28
                spacing: 20
                visible: !!page.light.id
                ColumnLayout {
                    spacing: 6
                    Label { text: "SELECTED LIGHT"; color: Theme.muted; font.pixelSize: 12; font.weight: Font.Bold; font.letterSpacing: 1 }
                    Label { text: page.light.name || ""; color: Theme.text; font.pixelSize: 20; font.weight: Font.ExtraBold }
                }
                RowLayout {   // Colour | White
                    id: modeTabs
                    property string mode: page.light.mode || "colour"
                    Layout.fillWidth: true
                    spacing: 4
                    Repeater {
                        model: page.light.hasColor ? [["colour", "Colour"], ["white", "White"]] : [["white", "White"]]
                        delegate: Button {
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: 40
                            readonly property bool on: modeTabs.mode === modelData[0]
                            onClicked: modeTabs.mode = modelData[0]
                            contentItem: Label { text: modelData[1]; color: parent.on ? Theme.text : Theme.mutedNav; font.weight: parent.on ? Font.ExtraBold : Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { radius: 9; color: parent.on ? Theme.lineStrong : Theme.well }
                        }
                    }
                }
                ColourWheel {
                    visible: modeTabs.mode === "colour"
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 240; Layout.preferredHeight: 240
                    current: page.light.hex || "white"
                    onPicked: (h, s) => backend.setLightHueSat(page.light.id, h, s)
                }
                ColumnLayout {
                    visible: modeTabs.mode === "white"
                    Layout.fillWidth: true
                    spacing: 8
                    Label { text: "Warm ← → Cool"; color: Theme.muted; font.pixelSize: 13 }
                    AmberSlider {
                        Layout.fillWidth: true
                        from: 500; to: 153            // mirek: warm (left) → cool (right)
                        liveValue: page.light.mirek || 366
                        trackGradient: ["#ff9a3c", "#cfe3ff"]
                        onMoved: backend.setLightMirek(page.light.id, value)
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Label { text: "Brightness"; color: Theme.muted; font.pixelSize: 13 }
                    AmberSlider {
                        Layout.fillWidth: true
                        liveValue: page.light.bri || 0
                        onMoved: backend.setLightBrightness(page.light.id, value)
                    }
                    Label { text: (page.light.bri || 0) + "%"; color: Theme.text; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight }
                }
                Label { text: "Quick whites"; color: Theme.muted; font.pixelSize: 13 }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2; columnSpacing: 8; rowSpacing: 8
                    Repeater {
                        model: backend.quickWhites
                        delegate: Button {
                            id: qw
                            required property var modelData
                            Layout.fillWidth: true; implicitHeight: 44
                            onClicked: backend.setLightMirek(page.light.id, modelData.mirek)
                            contentItem: Label { text: qw.modelData.label; color: Theme.text; font.weight: Font.Bold; verticalAlignment: Text.AlignVCenter; leftPadding: 4 }
                            background: Rectangle { radius: 12; color: qw.hovered ? Theme.raised : Theme.surface; border.color: Theme.lineStrong }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
