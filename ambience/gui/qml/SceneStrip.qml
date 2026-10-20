import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs

// Scenes in two rows, like the phone app: tiles flow top-to-bottom, then sideways, and
// the strip scrolls horizontally — a wider window simply shows more columns.
GridView {
    id: strip
    property bool selectOnClick: false     // Scenes page: click selects; Room page: click plays
    signal sceneClicked(string sceneId)

    flow: GridView.FlowTopToBottom
    cellWidth: 162; cellHeight: 124
    implicitHeight: count > 1 ? 2 * cellHeight : cellHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.HorizontalFlick
    // Not interactive: the page owns the vertical wheel. Sideways scrolling (touchpad swipe,
    // tilt wheel, or Shift+wheel) and the scrollbar still move the strip.
    interactive: false
    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded; interactive: true }
    SideScroll { flick: strip }

    delegate: SceneTile {
        onClicked: strip.selectOnClick ? backend.selectScene(item.id) : backend.recallScene(item.id)
        onMenuRequested: { menu.target = item; menu.popup() }
    }

    ThemedMenu {
        id: menu
        property var target: ({})
        ThemedMenuItem { text: "Play"; onTriggered: backend.recallScene(menu.target.id) }
        ThemedMenuItem {
            text: "Play dynamic"
            enabled: !!menu.target.dynamic
            onTriggered: backend.playScene(menu.target.id, true, menu.target.speed, menu.target.brightness)
        }
        MenuSeparator {}
        ThemedMenuItem { text: "Choose photo…"; onTriggered: photoDialog.open() }
        ThemedMenuItem { text: "Remove photo"; enabled: !!menu.target.photo; onTriggered: backend.clearScenePhoto(menu.target.id) }
        MenuSeparator {}
        ThemedMenuItem { text: "Delete scene…"; onTriggered: confirm.open() }
    }

    Dialog {   // deleting is permanent and reaches the phone app too, so it asks first
        id: confirm
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: 420
        padding: 24
        title: ""
        background: Rectangle { radius: 16; color: Theme.raised; border.color: Theme.lineStrong }
        Overlay.modal: Rectangle { color: "#99000000" }
        contentItem: Column {
            spacing: 14
            Label { width: parent.width; text: "Delete “" + (menu.target.name || "") + "”?"; color: Theme.text; font.pixelSize: 18; font.weight: Font.ExtraBold; wrapMode: Text.Wrap }
            Label {
                width: parent.width; wrapMode: Text.Wrap; color: Theme.textSoft
                text: "This removes the scene from your Hue Bridge, so it disappears from the phone app too. It can't be undone."
            }
            Row {
                anchors.right: parent.right
                spacing: 10
                Button {
                    id: cancelBtn
                    text: "Cancel"; implicitHeight: 40
                    onClicked: confirm.close()
                    contentItem: Label { text: cancelBtn.text; color: Theme.text; font.weight: Font.Bold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { implicitWidth: 96; radius: 20; color: cancelBtn.hovered ? Theme.lineStrong : Theme.surface; border.color: Theme.lineStrong }
                }
                Button {
                    id: deleteBtn
                    text: "Delete"; implicitHeight: 40
                    onClicked: { backend.deleteScene(menu.target.id); confirm.close() }
                    contentItem: Label { text: deleteBtn.text; color: "white"; font.weight: Font.ExtraBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { implicitWidth: 96; radius: 20; color: deleteBtn.hovered ? "#c0392b" : "#a8322a" }
                }
            }
        }
    }
    FileDialog {
        id: photoDialog
        title: "Choose a photo for " + (menu.target.name || "this scene")
        nameFilters: ["Pictures (*.jpg *.jpeg *.png *.webp *.bmp)"]
        onAccepted: backend.setScenePhoto(menu.target.id, selectedFile)
    }
}
