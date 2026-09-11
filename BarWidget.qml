import QtQuick
import Quickshell.Io
import qs.Ui
import qs.Commons

BarWidget {
    id: root
    moduleName: "io.github.mrc04d.proxima"

    readonly property string helper: Qt.resolvedUrl("helpers/proxima-helper.py").toString().replace(/^file:\/\//, "")
    readonly property string proximaDir: setting("proximaDir", "~/Work/Proxima")
    property bool alive: false
    property bool allLoggedIn: false
    property int loggedCount: 0
    property var providers: ({})
    property string lastError: ""

    function tooltipText() {
        if (!root.alive) return "Proxima — not running (click to launch on workspace 10)";
        var names = [];
        for (var k in root.providers) {
            if (root.providers[k] !== true) names.push(k);
        }
        if (root.allLoggedIn) return "Proxima — 4/4 logged in";
        return "Proxima — " + root.loggedCount + "/4" + (names.length > 0 ? ": " + names.join(", ") + " logged out" : "");
    }

    function applyStatus(text) {
        var line = String(text || "").trim().split("\n");
        var last = line[line.length - 1] || "";
        if (last === "") return;
        var obj = null;
        try { obj = JSON.parse(last); } catch (e) { root.lastError = "bad helper JSON"; return; }
        if (obj && obj.providers !== undefined) {
            root.alive = (obj.alive === true);
            root.allLoggedIn = (obj.allLoggedIn === true);
            root.loggedCount = Number(obj.count || 0);
            root.providers = obj.providers;
            root.lastError = String(obj.error || "");
        }
    }

    Process {
        id: statusProc
        command: ["python3", root.helper, "status"]
        environment: ({ "PROXIMA_DIR": root.proximaDir })
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: root.applyStatus(text)
        }
    }

    Timer {
        interval: Math.min(120, Math.max(10, setting("pollIntervalSec", 30))) * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            interval = Math.min(120, Math.max(10, setting("pollIntervalSec", 30))) * 1000;
            if (!statusProc.running) statusProc.running = true;
        }
    }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        // Must stay monochrome so activeColor applies: U+26A1 "⚡" falls
        // through to Noto Color Emoji (fixed yellow, ignores color); U+F02A9
        // robot clashed with another widget. U+25C9 FISHEYE ships in
        // JetBrainsMono Nerd Font (monochrome) — a status dot.
        text: "◉"
        active: true
        useActiveColor: true
        activeColor: !root.alive ? "#6e7681" : (root.allLoggedIn ? "#3fb950" : "#d29922")
        tooltipText: root.tooltipText()
        onPressed: function(btn) {
            if (btn === Qt.MiddleButton) { if (!statusProc.running) statusProc.running = true; return; }
            if (btn !== Qt.LeftButton) return;
            if (root.bar) root.bar.run("PROXIMA_DIR=" + Util.shellQuote(root.proximaDir) + " python3 " + Util.shellQuote(root.helper) + " show");
            refreshTimer.restart();
        }
    }

    Timer {
        id: refreshTimer
        interval: 3000
        running: false
        repeat: false
        onTriggered: if (!statusProc.running) statusProc.running = true
    }
}
