import QtQuick
import QtQuick.Shapes

// "Glow" thumbnail: colours as soft pools of light on a dark wall. Same recipe as the
// mockup's CSS: each colour is a radial gradient at a fixed spot (so a scene's image is
// stable), stops at 0 / 45 % / 100 % of that spot's reach, measured to the farthest
// corner. One colour = one big centred glow.
Item {
    id: root
    property var colors: []
    property real topRadius: 0
    property real bottomRadius: 0

    readonly property var spots: [[0.22, 0.30, 0.62], [0.78, 0.22, 0.58], [0.50, 0.88, 0.66],
                                  [0.12, 0.92, 0.52], [0.90, 0.80, 0.54]]

    Rectangle {
        anchors.fill: parent
        color: Theme.glowBase
        topLeftRadius: root.topRadius; topRightRadius: root.topRadius
        bottomLeftRadius: root.bottomRadius; bottomRightRadius: root.bottomRadius
    }

    Repeater {
        model: Math.min(root.colors.length, 5)
        Shape {
            id: pool
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            readonly property bool single: root.colors.length === 1
            readonly property var spot: single ? [0.5, 0.6, 0.72] : root.spots[index]
            readonly property color c: root.colors[index]
            readonly property real cx: root.width * spot[0]
            readonly property real cy: root.height * spot[1]
            // CSS "circle" sizes to the farthest corner; stop percentages are of that
            readonly property real reach: Math.max(Math.hypot(cx, cy), Math.hypot(root.width - cx, cy),
                                                   Math.hypot(cx, root.height - cy),
                                                   Math.hypot(root.width - cx, root.height - cy))
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: pool.cx; centerY: pool.cy; centerRadius: pool.reach * pool.spot[2]
                    focalX: pool.cx; focalY: pool.cy; focalRadius: 0
                    GradientStop { position: 0.0; color: Qt.rgba(pool.c.r, pool.c.g, pool.c.b, pool.single ? 0.8 : 0.85) }
                    GradientStop { position: 0.45; color: Qt.rgba(pool.c.r, pool.c.g, pool.c.b, 0.33) }
                    GradientStop { position: 1.0; color: Qt.rgba(pool.c.r, pool.c.g, pool.c.b, 0) }
                }
                PathRectangle {
                    x: 0; y: 0; width: root.width; height: root.height
                    topLeftRadius: root.topRadius; topRightRadius: root.topRadius
                    bottomLeftRadius: root.bottomRadius; bottomRightRadius: root.bottomRadius
                }
            }
        }
    }
}
