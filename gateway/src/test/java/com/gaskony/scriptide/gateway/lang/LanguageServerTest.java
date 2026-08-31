package com.gaskony.scriptide.gateway.lang;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** JSON-RPC handling and the call-site arithmetic behind signature help. */
class LanguageServerTest {

    private static LanguageServer server() {
        // A null ScriptManager exercises the "no gateway" path: HintIndex must
        // degrade to empty rather than throw, so the editor still works without
        // completions instead of the whole channel dying.
        return new LanguageServer(() -> null);
    }

    private static JsonObject request(String method, JsonObject params, Integer id) {
        JsonObject m = new JsonObject();
        m.addProperty("jsonrpc", "2.0");
        m.addProperty("method", method);
        m.add("params", params);
        if (id != null) {
            m.addProperty("id", id);
        }
        return m;
    }

    @Test
    @DisplayName("initialize advertises incremental sync and the trigger characters")
    void initializeAdvertisesCapabilities() {
        JsonObject response = server().handle(request("initialize", new JsonObject(), 1));
        JsonObject caps = response.getAsJsonObject("result").getAsJsonObject("capabilities");
        // 2 = Incremental. Full sync re-sends the whole document per keystroke.
        assertThat(caps.get("textDocumentSync").getAsInt()).isEqualTo(2);
        assertThat(caps.getAsJsonObject("completionProvider")
            .getAsJsonArray("triggerCharacters").get(0).getAsString()).isEqualTo(".");
        assertThat(caps.getAsJsonObject("completionProvider")
            .get("resolveProvider").getAsBoolean()).isTrue();
        assertThat(caps.get("hoverProvider").getAsBoolean()).isTrue();
    }

    @Test
    @DisplayName("a notification gets no reply; a request always does")
    void notificationsGetNoReply() {
        LanguageServer s = server();
        // Replying to a notification is a protocol violation and confuses clients.
        assertThat(s.handle(request("initialized", new JsonObject(), null))).isNull();
        assertThat(s.handle(request("initialize", new JsonObject(), 7))).isNotNull();
    }

    @Test
    @DisplayName("an unknown method answers null rather than erroring")
    void unknownMethodIsQuiet() {
        // Clients probe for optional capabilities; erroring on each fills the
        // console with what looks like faults.
        JsonObject response = server().handle(
            request("textDocument/codeLens", new JsonObject(), 3));
        assertThat(response.has("result")).isTrue();
        assertThat(response.has("error")).isFalse();
    }

    @Test
    @DisplayName("didOpen then didClose tracks the open document set")
    void tracksOpenDocuments() {
        LanguageServer s = server();
        JsonObject open = new JsonObject();
        JsonObject td = new JsonObject();
        td.addProperty("uri", "ignition://p/a");
        td.addProperty("text", "x = 1\n");
        td.addProperty("version", 1);
        open.add("textDocument", td);
        s.handle(request("textDocument/didOpen", open, null));
        assertThat(s.openDocumentCount()).isEqualTo(1);

        JsonObject close = new JsonObject();
        JsonObject id = new JsonObject();
        id.addProperty("uri", "ignition://p/a");
        close.add("textDocument", id);
        s.handle(request("textDocument/didClose", close, null));
        assertThat(s.openDocumentCount()).isZero();
    }

    @Test
    @DisplayName("completion on an unknown document returns an empty list, not an error")
    void completionOnUnknownDocument() {
        JsonObject params = new JsonObject();
        JsonObject td = new JsonObject();
        td.addProperty("uri", "ignition://p/missing");
        params.add("textDocument", td);
        JsonObject pos = new JsonObject();
        pos.addProperty("line", 0);
        pos.addProperty("character", 0);
        params.add("position", pos);

        JsonObject result = server().handle(request("textDocument/completion", params, 5))
            .getAsJsonObject("result");
        assertThat(result.getAsJsonArray("items")).isEmpty();
        assertThat(result.get("isIncomplete").getAsBoolean()).isFalse();
    }

    @Test
    @DisplayName("the open paren of the CURRENT call is found, not a nested one")
    void findsEnclosingCall() {
        // foo(bar(1), | -> the cursor is an argument of foo, not of bar.
        String line = "system.tag.writeBlocking(paths(1), ";
        int open = LanguageServer.openCallParen(line, line.length());
        assertThat(line.substring(0, open)).isEqualTo("system.tag.writeBlocking");
    }

    @Test
    @DisplayName("no enclosing call is reported when the cursor is outside one")
    void noEnclosingCall() {
        assertThat(LanguageServer.openCallParen("x = 1", 5)).isEqualTo(-1);
        assertThat(LanguageServer.openCallParen("foo(1)", 6)).isEqualTo(-1);
    }

    @Test
    @DisplayName("the active parameter counts only top-level commas")
    void countsActiveParameter() {
        String line = "f(a, g(b, c), ";
        int open = LanguageServer.openCallParen(line, line.length());
        // Commas inside g(...) belong to g, not to f.
        assertThat(LanguageServer.countArgumentsBefore(line, open, line.length())).isEqualTo(2);
    }

    @Test
    @DisplayName("the outline survives a transient syntax error")
    void outlineSurvivesTransientSyntaxError() {
        // A buffer is unparseable for most of the time someone is typing. Blanking
        // the outline on every keystroke is worse than showing a slightly stale one.
        LanguageServer s = server();
        String uri = "ignition://p/m";

        JsonObject open = new JsonObject();
        JsonObject td = new JsonObject();
        td.addProperty("uri", uri);
        td.addProperty("text", "def alpha():\n\tpass\n");
        td.addProperty("version", 1);
        open.add("textDocument", td);
        s.handle(request("textDocument/didOpen", open, null));

        JsonObject idParams = new JsonObject();
        JsonObject idDoc = new JsonObject();
        idDoc.addProperty("uri", uri);
        idParams.add("textDocument", idDoc);
        var before = s.handle(request("textDocument/documentSymbol", idParams, 10))
            .getAsJsonArray("result");
        assertThat(before).hasSize(1);

        // Now break it, the way a half-typed call does.
        JsonObject change = new JsonObject();
        JsonObject changeDoc = new JsonObject();
        changeDoc.addProperty("uri", uri);
        changeDoc.addProperty("version", 2);
        change.add("textDocument", changeDoc);
        com.google.gson.JsonArray changes = new com.google.gson.JsonArray();
        JsonObject full = new JsonObject();
        full.addProperty("text", "def alpha():\n\tpass\n\nx = foo(\n");
        changes.add(full);
        change.add("contentChanges", changes);
        s.handle(request("textDocument/didChange", change, null));

        var after = s.handle(request("textDocument/documentSymbol", idParams, 11))
            .getAsJsonArray("result");
        assertThat(after)
            .as("the outline should hold the last good parse, not empty out")
            .hasSize(1);
        assertThat(after.get(0).getAsJsonObject().get("name").getAsString())
            .isEqualTo("alpha");
    }

    @Test
    @DisplayName("hover resolves the whole name under the cursor, not just what precedes it")
    void hoverUsesFullName() {
        TextDocument d = new TextDocument("u", "system.tag.readBlocking(x)\n", 1);
        // Cursor in the MIDDLE of readBlocking.
        assertThat(LanguageServer.fullDottedNameAt(d, 0, 15))
            .isEqualTo("system.tag.readBlocking");
    }
}
