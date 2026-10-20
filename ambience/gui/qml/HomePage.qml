import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Flickable {
    id: page
    signal openRoom(string roomId)
    contentHeight: column.implicitHeight + 64
    clip: true
    ScrollBar.vertical: ScrollBar {}
    FastWheel { flick: page }

    ColumnLayout {
        id: column
        x: 40; y: 32
        width: page.width - 80
        spacing: 28

        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 6
                Label { text: "Home"; color: Theme.text; font.pixelSize: 30; font.weight: Font.ExtraBold }
                Label { text: backend.summary; color: Theme.muted; font.pixelSize: 14 }
            }
            Item { Layout.fillWidth: true }
            Button {
                id: allOff
                text: "All lights off"
                implicitHeight: 44
                onClicked: backend.setAllOn(false)
                contentItem: Label { text: allOff.text; color: Theme.text; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: 22; color: allOff.hovered ? Theme.raised : Theme.surface; border.color: "#343843"; implicitWidth: 140 }
            }
        }

        Label { text: "ROOMS & ZONES"; color: Theme.muted; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1 }

        GridLayout {
            Layout.fillWidth: true
            columns: Math.max(1, Math.floor((page.width - 80 + 16) / (276 + 16)))
            columnSpacing: 16; rowSpacing: 16

            Repeater {
                model: backend.roomsModel
                delegate: Rectangle {
                    id: card
                    required property var item
                    Layout.fillWidth: true
                    Layout.preferredHeight: 214
                    radius: 16
                    color: Theme.surface
                    border.color: hover.hovered ? Theme.lineStrong : Theme.line

                    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: page.openRoom(card.item.id) }

                    Glow {
                        id: glow
                        x: 1; y: 1; width: parent.width - 2; height: 96
                        topRadius: 15
                        colors: card.item.on ? card.item.glow : ["#2a2e37"]
                    }
                    ColumnLayout {
                        anchors { left: parent.left; right: parent.right; top: glow.bottom; margins: 18; topMargin: 16 }
                        spacing: 14
                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout {
                                spacing: 4
                                Label { text: card.item.name; color: Theme.text; font.pixelSize: 17; font.weight: Font.ExtraBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: card.item.meta; color: Theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            Toggle {
                                liveChecked: card.item.on
                                enabled: card.item.groupedId !== ""
                                onToggled: backend.setGroupOn(card.item.groupedId, checked)
                                Accessible.name: card.item.name + " power"
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            AmberSlider {
                                Layout.fillWidth: true
                                liveValue: card.item.bri
                                enabled: card.item.on
                                onMoved: backend.setGroupBrightness(card.item.groupedId, value)
                                Accessible.name: card.item.name + " brightness"
                            }
                            Label { text: card.item.on ? card.item.bri + "%" : "Off"; color: Theme.textSoft; font.pixelSize: 13; Layout.preferredWidth: 40; horizontalAlignment: Text.AlignRight }
                        }
                    }
                }
            }
        }
    }
}
