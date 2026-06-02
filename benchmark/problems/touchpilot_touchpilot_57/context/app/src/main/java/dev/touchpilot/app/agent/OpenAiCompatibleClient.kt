package dev.touchpilot.app.agent

import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class OpenAiCompatibleClient(
    private val config: ProviderConfig
) {
    fun complete(systemPrompt: String, userPrompt: String): String {
        val body = JSONObject()
            .put("model", config.model)
            .put("temperature", 0)
            .put(
                "messages",
                JSONArray()
                    .put(JSONObject().put("role", "system").put("content", systemPrompt))
                    .put(JSONObject().put("role", "user").put("content", userPrompt))
            )

        val connection = URL(config.baseUrl).openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = 30_000
        connection.readTimeout = 60_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        if (config.apiKey.isNotBlank()) {
            connection.setRequestProperty("Authorization", "Bearer ${config.apiKey}")
        }

        OutputStreamWriter(connection.outputStream).use { writer ->
            writer.write(body.toString())
        }

        val responseText = if (connection.responseCode in 200..299) {
            connection.inputStream.bufferedReader().use { it.readText() }
        } else {
            val errorText = connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
            error("Provider returned HTTP ${connection.responseCode}: $errorText")
        }

        val response = JSONObject(responseText)
        return response
            .getJSONArray("choices")
            .getJSONObject(0)
            .getJSONObject("message")
            .optString("content")
    }
}
