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
    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

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
    }
    FileDialog {
        id: photoDialog
        title: "Choose a photo for " + (menu.target.name || "this scene")
        nameFilters: ["Pictures (*.jpg *.jpeg *.png *.webp *.bmp)"]
        onAccepted: backend.setScenePhoto(menu.target.id, selectedFile)
    }
}
