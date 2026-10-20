import QtQuick
import QtQuick.Controls.Basic

// Qt's Basic menu is white; this is the app's dark version (items: ThemedMenuItem).
Menu {
    padding: 6
    background: Rectangle {
        implicitWidth: 220
        radius: 12
        color: Theme.raised
        border.color: Theme.lineStrong
    }
}
