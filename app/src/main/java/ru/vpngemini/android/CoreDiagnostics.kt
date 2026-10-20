// SPDX-License-Identifier: GPL-3.0-or-later
package ru.vpngemini.android

object CoreDiagnostics {
    private val ansi = Regex("\u001B\\[[0-?]*[ -/]*[@-~]")
    fun clean(text: String, server: Server): String {
        var result = ansi.replace(text, "")
        val secrets = listOf(server.raw, server.password, server.user,
            server.params["obfs-password"].orEmpty(), server.params["obfs_password"].orEmpty())
        secrets.filter { it.length > 3 }.distinct().sortedByDescending { it.length }.forEach {
            result = result.replace(it, "***")
        }
        return result
    }
}
