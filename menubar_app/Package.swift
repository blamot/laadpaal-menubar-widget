// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LaadpaalMenubar",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "LaadpaalMenubar", targets: ["LaadpaalMenubar"])
    ],
    targets: [
        .executableTarget(
            name: "LaadpaalMenubar",
            path: "Sources"
        )
    ]
)
