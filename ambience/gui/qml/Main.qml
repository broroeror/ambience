import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1280; height: 820
    minimumWidth: 900; minimumHeight: 600
    visible: true
    title: "Ambience"
    color: Theme.ground

    property int page: 0          // 0 home, 1 room, 2 scenes

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {   // sidebar
            Layout.preferredWidth: 232; Layout.fillHeight: true
            color: Theme.sidebar
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.line }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 16; anchors.topMargin: 24
                spacing: 6
                RowLayout {
                    Layout.leftMargin: 10; Layout.bottomMargin: 22
                    spacing: 10
                    Rectangle {
                        width: 26; height: 26; radius: 13; color: "transparent"; border.color: Theme.accent; border.width: 2
                        Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: Theme.accent }
                    }
                    Label { text: "Ambience"; color: Theme.text; font.pixelSize: 18; font.weight: Font.ExtraBold }
                }
                Repeater {
                    model: [{ label: "Home", ready: true, page: 0 }, { label: "Scenes", ready: true, page: 2 },
                            { label: "Sync", ready: false, page: -1 }, { label: "Settings", ready: false, page: -1 }]
                    delegate: Button {
                        id: nav
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true; implicitHeight: 44
                        enabled: modelData.ready
                        // the Room page belongs to Home
                        readonly property bool current: modelData.page === (win.page === 1 ? 0 : win.page)
                        onClicked: win.page = modelData.page
                        contentItem: RowLayout {
                            Label { text: nav.modelData.label; color: nav.current ? Theme.text : Theme.mutedNav; font.weight: nav.current ? Font.Bold : Font.DemiBold; Layout.fillWidth: true; leftPadding: 4 }
                            Label { visible: !nav.modelData.ready; text: "soon"; color: Theme.muted; font.pixelSize: 11 }
                        }
                        background: Rectangle { radius: 10; color: nav.current ? Theme.raised : (nav.hovered ? Theme.surface : "transparent") }
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle {   // bridge status
                    Layout.fillWidth: true; implicitHeight: 62; radius: 10; color: Theme.surface
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 12; spacing: 4
                        RowLayout {
                            spacing: 8
                            Rectangle { width: 8; height: 8; radius: 4; color: backend.connected ? Theme.ok : Theme.accent }
                            Label { text: "Hue Bridge"; color: Theme.text; font.weight: Font.Bold; font.pixelSize: 13 }
                        }
                        Label {
                            text: !backend.paired ? "Not paired" : (backend.connected ? "Live · " : "Reconnecting · ") + backend.bridgeLabel
                            color: Theme.muted; font.pixelSize: 12
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: backend.paired ? win.page : 3
            HomePage {
                onOpenRoom: (rid) => { backend.openRoom(rid); win.page = 1 }
            }
            RoomPage { onBack: win.page = 0 }
            ScenesPage {}
            Item {   // not paired yet
                ColumnLayout {
                    anchors.centerIn: parent; spacing: 10
                    Label { text: "Not paired with a bridge yet"; color: Theme.text; font.pixelSize: 22; font.weight: Font.ExtraBold }
                    Label { text: "For now, pair from a terminal:  python -m ambience pair"; color: Theme.muted }
                }
            }
        }
    }

    Rectangle {   // notice toast (e.g. "Added … to …")
        visible: backend.notice !== "" && backend.error === ""
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 20 }
        width: Math.min(parent.width - 80, noticeLabel.implicitWidth + 32); height: noticeLabel.implicitHeight + 20
        radius: 12; color: Theme.raised; border.color: Theme.lineStrong
        Label { id: noticeLabel; anchors.centerIn: parent; text: backend.notice; color: Theme.text }
    }

    Rectangle {   // error toast
        visible: backend.error !== ""
        anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 20 }
        width: Math.min(parent.width - 80, errLabel.implicitWidth + 32); height: errLabel.implicitHeight + 20
        radius: 12; color: "#2a1518"; border.color: "#6b2a33"
        Label { id: errLabel; anchors.centerIn: parent; width: parent.width - 32; text: backend.error; color: "#ffd0d4"; wrapMode: Text.Wrap }
    }
}
