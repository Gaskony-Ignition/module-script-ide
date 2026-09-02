package com.gaskony.scriptide.gateway.term;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.Channels;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * A very small Docker Engine API client, speaking HTTP/1.1 over the daemon's
 * Unix socket, for one purpose: running a shell inside a container as root.
 *
 * <h2>Why this exists at all</h2>
 *
 * <p>This is how every Docker UI opens a root terminal in one click, and Nigel
 * asked for that shape (02/09/2026) because a gateway installed directly on a
 * machine would just be given a real terminal — the browser terminal earns its
 * keep on a <b>containerised</b> gateway, which is exactly the case this
 * handles.</p>
 *
 * <p>The mechanism is worth stating precisely, because it is the opposite of the
 * {@code sudo} route beside it. A process cannot raise its own privilege; only
 * something more privileged can create a privileged process on its behalf. The
 * Docker daemon runs as <b>root on the host</b>, so when it is asked for an exec
 * with {@code User: "0"} it simply creates one — no setuid binary, no sudoers
 * rule, nothing installed in the image.</p>
 *
 * <h2>Why no library, and no docker CLI</h2>
 *
 * <p>docker-java and friends are large, and shipping one through
 * {@code modlImplementation} to make four HTTP requests is not a trade worth
 * making. Shelling out to a {@code docker} binary would put a dependency back in
 * the image, which is the thing this route exists to remove. Java 17 has Unix
 * domain sockets in the JDK ({@link StandardProtocolFamily#UNIX}), so the whole
 * client is the four calls below.</p>
 *
 * <h2>What is deliberately NOT here</h2>
 *
 * <p>Nothing that creates, starts, stops or removes a container, and no image
 * operations. This class execs into <b>one</b> container — the one the caller
 * names, which is always this JVM's own. That is a self-imposed limit rather
 * than a security boundary: anyone who can reach this socket can do all of those
 * things by other means, which is exactly why SECURITY.md treats socket access
 * as host root and says so in those words.</p>
 */
public final class DockerExec {

    private static final Logger logger = LoggerFactory.getLogger(DockerExec.class);

    /**
     * Pinned API version.
     *
     * <p>Well inside the daemon's supported window — a current daemon advertises
     * {@code ApiVersion 1.54, MinAPIVersion 1.40} (measured 02/09/2026). Pinning
     * rather than negotiating: the four endpoints used here have been stable
     * since 1.24, and a version request is a round trip that buys nothing.</p>
     */
    private static final String API = "/v1.41";

    /** Where the daemon listens, best first. */
    private static final List<String> SOCKET_CANDIDATES =
        List.of("/var/run/docker.sock", "/run/docker.sock");

    /** A control request is tiny; a daemon that has not answered by now is gone. */
    private static final int CONTROL_TIMEOUT_MS = 5000;

    private static final Gson GSON = new Gson();

    private DockerExec() { /* static factory */ }

    /** The daemon socket this host exposes, or {@code null} for none. */
    public static Path socketPath() {
        for (String candidate : SOCKET_CANDIDATES) {
            Path path = Path.of(candidate);
            // isReadable is not enough: a socket we cannot WRITE to is a socket
            // we cannot use, and that is the common failure — the socket is
            // root:docker 0660 and the Gateway's user is in neither.
            if (Files.exists(path) && Files.isReadable(path) && Files.isWritable(path)) {
                return path;
            }
        }
        return null;
    }

    /**
     * Whether a root shell is obtainable through the daemon right now.
     *
     * <p>Proved by asking, exactly as the sudo probe is: the socket is inspected
     * for existence and then <b>used</b>, because a socket that exists and
     * refuses us is indistinguishable from one that works until you try it.</p>
     */
    public static boolean available(String containerId) {
        if (containerId == null) {
            return false;
        }
        Path socket = socketPath();
        if (socket == null) {
            return false;
        }
        try {
            JsonObject info = get(socket, API + "/containers/" + containerId + "/json");
            // Also confirms the id is OUR container and still running — a stale
            // id from a recycled mountinfo would otherwise fail at exec time,
            // by which point the user is looking at a blank terminal.
            return info != null
                && info.has("State")
                && info.getAsJsonObject("State").get("Running").getAsBoolean();
        } catch (Exception e) {
            // WARN, not debug. Somebody deliberately mounted this socket, and
            // the only symptom of it not working is an unprivileged shell —
            // which looks exactly like a gateway where it was never mounted at
            // all. This was logged at debug in the first version and cost a
            // whole diagnosis: `SocketChannel.socket()` throws
            // UnsupportedOperationException on a Unix-domain channel, so every
            // request failed, and the route reported itself simply absent.
            logger.warn("The Docker socket at {} is mounted but not usable, so the terminal "
                + "will not be able to elevate: {}", socket, e.toString());
            return false;
        }
    }

    /**
     * Start a root shell in {@code containerId} and hand back its raw stream.
     *
     * @param shell absolute path, already validated by {@link TerminalPolicy}
     */
    public static Session start(String containerId, String shell, String workingDir,
                                int cols, int rows) throws IOException {
        Path socket = socketPath();
        if (socket == null) {
            throw new IOException("no Docker socket");
        }

        JsonObject create = new JsonObject();
        create.addProperty("AttachStdin", true);
        create.addProperty("AttachStdout", true);
        create.addProperty("AttachStderr", true);
        // Tty:true is doing two jobs. It gives the shell a real pty inside the
        // container — so job control, line editing and `stty size` all work —
        // AND it makes the attached stream RAW. With Tty:false the daemon
        // multiplexes stdout and stderr behind an 8-byte frame header, which
        // would arrive at xterm.js as garbage every few hundred bytes.
        create.addProperty("Tty", true);
        create.addProperty("User", "0");
        if (workingDir != null && !workingDir.isBlank()) {
            create.addProperty("WorkingDir", workingDir);
        }
        create.add("Cmd", GSON.toJsonTree(List.of(shell, "-i")));
        // A login-ish environment. TERM is what makes xterm.js and the shell
        // agree on capabilities; the pagers are because nothing in a browser
        // terminal can drive `less`, and a pager waiting for a key it will never
        // receive looks exactly like a hung command.
        create.add("Env", GSON.toJsonTree(List.of(
            "TERM=xterm-256color", "PAGER=cat", "GIT_PAGER=cat",
            "COLUMNS=" + cols, "LINES=" + rows)));

        JsonObject created = post(socket, API + "/containers/" + containerId + "/exec", create);
        if (created == null || !created.has("Id")) {
            throw new IOException("Docker refused the exec: " + created);
        }
        String execId = created.get("Id").getAsString();

        // The size must be set BEFORE the stream is attached. Afterwards the
        // shell has already drawn its first prompt at 80x24 and the redraw is
        // visible.
        resize(socket, execId, cols, rows);

        // The hijack. This connection stops being HTTP once the headers are
        // read and becomes the terminal itself, so it is never reused for
        // anything else and every later control call opens its own.
        SocketChannel channel = SocketChannel.open(UnixDomainSocketAddress.of(socket.toString()));
        try {
            JsonObject startBody = new JsonObject();
            startBody.addProperty("Detach", false);
            startBody.addProperty("Tty", true);
            byte[] payload = GSON.toJson(startBody).getBytes(StandardCharsets.UTF_8);

            OutputStream out = Channels.newOutputStream(channel);
            out.write(("POST " + API + "/exec/" + execId + "/start HTTP/1.1\r\n"
                + "Host: docker\r\n"
                + "Content-Type: application/json\r\n"
                + "Connection: Upgrade\r\n"
                + "Upgrade: tcp\r\n"
                + "Content-Length: " + payload.length + "\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
            out.write(payload);
            out.flush();

            InputStream in = Channels.newInputStream(channel);
            String status = readHeaders(in);
            // 101 on a successful upgrade, 200 when the daemon answers without
            // upgrading — both leave the stream attached and both are fine.
            if (!status.contains(" 101") && !status.contains(" 200")) {
                throw new IOException("Docker would not attach: " + status);
            }
            return new Session(socket, execId, channel, in, out);
        } catch (IOException e) {
            closeQuietly(channel);
            throw e;
        }
    }

    /** One attached exec: the raw stream plus the calls that steer it. */
    public static final class Session {
        private final Path socket;
        private final String execId;
        private final SocketChannel channel;
        private final InputStream in;
        private final OutputStream out;

        private Session(Path socket, String execId, SocketChannel channel,
                        InputStream in, OutputStream out) {
            this.socket = socket;
            this.execId = execId;
            this.channel = channel;
            this.in = in;
            this.out = out;
        }

        public InputStream output() {
            return in;
        }

        /**
         * Send keystrokes to the shell.
         *
         * <p>A method rather than a getter for the {@code OutputStream}. Handing
         * the stream out let a caller close it independently of the session,
         * which on a hijacked connection half-closes the terminal and leaves an
         * exec the daemon still thinks is attached — and SpotBugs flags the
         * escape (EI) for exactly that reason.</p>
         */
        public void write(byte[] data) throws IOException {
            out.write(data);
            out.flush();
        }

        /**
         * Resize the container-side pty.
         *
         * <p>A real API call, not an {@code stty} typed at the shell — so no
         * command appears at the user's prompt every time the panel is dragged,
         * and it works even while a full-screen program has the terminal.</p>
         */
        public void resize(int cols, int rows) {
            DockerExec.resize(socket, execId, cols, rows);
        }

        /** Exit code once the shell has ended, or {@code null} while it runs. */
        public Integer exitCode() {
            try {
                JsonObject state = get(socket, API + "/exec/" + execId + "/json");
                if (state == null || state.get("Running").getAsBoolean()) {
                    return null;
                }
                return state.has("ExitCode") && !state.get("ExitCode").isJsonNull()
                    ? state.get("ExitCode").getAsInt() : 0;
            } catch (Exception e) {
                return null;
            }
        }

        /**
         * End the shell by closing the stream.
         *
         * <p>Closing the hijacked connection hangs up the container-side pty and
         * the shell exits on SIGHUP — the same way any terminal session ends.
         * There is no "kill this exec" endpoint in the Engine API, and there is
         * no need for one: the process is the daemon's child, not ours, so this
         * works whether the shell is root or not. That is a real advantage over
         * the sudo route, where the JVM cannot signal a root child at all.</p>
         */
        public void close() {
            closeQuietly(channel);
        }

        public boolean isAlive() {
            return channel.isOpen();
        }
    }

    // ---- the four requests -------------------------------------------------

    private static void resize(Path socket, String execId, int cols, int rows) {
        try {
            get(socket, API + "/exec/" + execId + "/resize?h=" + rows + "&w=" + cols, "POST");
        } catch (Exception e) {
            // Best effort by design: a failed resize costs a redraw, and failing
            // loudly here would be noise on every window drag.
            logger.debug("Docker resize failed: {}", e.toString());
        }
    }

    private static JsonObject get(Path socket, String path) throws IOException {
        return get(socket, path, "GET");
    }

    private static JsonObject get(Path socket, String path, String method) throws IOException {
        try (SocketChannel channel = connect(socket)) {
            java.util.concurrent.ScheduledFuture<?> watchdog = withTimeout(channel);
            try {
                OutputStream out = Channels.newOutputStream(channel);
                out.write((method + " " + path + " HTTP/1.1\r\nHost: docker\r\n"
                    + "Content-Length: 0\r\nConnection: close\r\n\r\n")
                    .getBytes(StandardCharsets.UTF_8));
                out.flush();
                return readJsonResponse(Channels.newInputStream(channel));
            } finally {
                watchdog.cancel(false);
            }
        }
    }

    private static JsonObject post(Path socket, String path, JsonObject body) throws IOException {
        byte[] payload = GSON.toJson(body).getBytes(StandardCharsets.UTF_8);
        try (SocketChannel channel = connect(socket)) {
            java.util.concurrent.ScheduledFuture<?> watchdog = withTimeout(channel);
            try {
                OutputStream out = Channels.newOutputStream(channel);
                out.write(("POST " + path + " HTTP/1.1\r\nHost: docker\r\n"
                    + "Content-Type: application/json\r\n"
                    + "Content-Length: " + payload.length + "\r\nConnection: close\r\n\r\n")
                    .getBytes(StandardCharsets.UTF_8));
                out.write(payload);
                out.flush();
                return readJsonResponse(Channels.newInputStream(channel));
            } finally {
                watchdog.cancel(false);
            }
        }
    }

    /**
     * A daemon-thread watchdog, so a wedged Docker daemon cannot hang a caller.
     *
     * <p>One thread for the whole module, and a daemon one so it never holds up
     * JVM shutdown. Needed because a blocking channel has no read timeout of its
     * own and the calling thread here is a user's terminal-open click.</p>
     */
    private static final java.util.concurrent.ScheduledExecutorService WATCHDOG =
        java.util.concurrent.Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "script-ide-docker-watchdog");
            thread.setDaemon(true);
            return thread;
        });

    /**
     * Open a control connection to the daemon.
     *
     * <p><b>Do not reintroduce {@code channel.socket().setSoTimeout(...)} here.</b>
     * {@link SocketChannel#socket()} is specified to throw
     * {@code UnsupportedOperationException} for a channel that is not IP-based,
     * and a Unix-domain channel is not. The first version of this method called
     * it, so every single control request threw, {@code available()} caught it
     * as "the socket is unusable", and the whole Docker route reported itself
     * absent — on a host where it was mounted and working. The only symptom was
     * an unprivileged shell and one log line reading {@code elevation=none}.</p>
     *
     * <p>Timeouts come from {@link #withTimeout} instead: closing a blocked
     * channel raises {@code AsynchronousCloseException} on the thread stuck in
     * the read, which is the supported way to interrupt one.</p>
     */
    private static SocketChannel connect(Path socket) throws IOException {
        return SocketChannel.open(UnixDomainSocketAddress.of(socket.toString()));
    }

    /** Close {@code channel} after the control timeout, unblocking any read. */
    private static java.util.concurrent.ScheduledFuture<?> withTimeout(SocketChannel channel) {
        return WATCHDOG.schedule(() -> {
            if (channel.isOpen()) {
                logger.debug("Docker control request timed out; closing the connection");
                closeQuietly(channel);
            }
        }, CONTROL_TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS);
    }

    // ---- HTTP, by hand -----------------------------------------------------

    /**
     * Read the status line and headers, byte at a time, stopping at the blank
     * line.
     *
     * <p>Byte at a time on purpose. A {@code BufferedReader} would read ahead
     * into the body — and on the hijacked connection the "body" is the terminal
     * stream, so the first thing the user typed at would already have been
     * swallowed by a buffer nobody reads again. This is slow and correct, over a
     * few hundred bytes, once per connection.</p>
     *
     * @return the status line
     */
    private static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int consecutiveNewlines = 0;
        int b;
        while ((b = in.read()) != -1) {
            buffer.write(b);
            if (b == '\n') {
                consecutiveNewlines++;
                if (consecutiveNewlines == 2) {
                    break;
                }
            } else if (b != '\r') {
                consecutiveNewlines = 0;
            }
        }
        String headers = buffer.toString(StandardCharsets.UTF_8);
        int eol = headers.indexOf('\n');
        return eol > 0 ? headers.substring(0, eol).trim() : headers.trim();
    }

    /** Headers, then a body that may be either length-delimited or chunked. */
    private static JsonObject readJsonResponse(InputStream in) throws IOException {
        ByteArrayOutputStream head = new ByteArrayOutputStream();
        int consecutiveNewlines = 0;
        int b;
        while ((b = in.read()) != -1) {
            head.write(b);
            if (b == '\n') {
                consecutiveNewlines++;
                if (consecutiveNewlines == 2) {
                    break;
                }
            } else if (b != '\r') {
                consecutiveNewlines = 0;
            }
        }
        String headers = head.toString(StandardCharsets.UTF_8);
        String body = headers.toLowerCase(java.util.Locale.ROOT).contains("transfer-encoding: chunked")
            ? readChunked(in)
            : new String(in.readAllBytes(), StandardCharsets.UTF_8);
        String trimmed = body.trim();
        if (trimmed.isEmpty() || !trimmed.startsWith("{")) {
            return null;
        }
        return GSON.fromJson(trimmed, JsonObject.class);
    }

    private static String readChunked(InputStream in) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        while (true) {
            StringBuilder sizeLine = new StringBuilder();
            int b;
            while ((b = in.read()) != -1 && b != '\n') {
                if (b != '\r') {
                    sizeLine.append((char) b);
                }
            }
            int size;
            try {
                // A chunk header may carry extensions after a ';'.
                String hex = sizeLine.toString().split(";")[0].trim();
                size = hex.isEmpty() ? 0 : Integer.parseInt(hex, 16);
            } catch (NumberFormatException e) {
                break;
            }
            if (size == 0) {
                break;
            }
            byte[] chunk = in.readNBytes(size);
            body.write(chunk);
            // The CRLF that terminates the chunk.
            in.readNBytes(2);
        }
        return body.toString(StandardCharsets.UTF_8);
    }

    private static void closeQuietly(SocketChannel channel) {
        try {
            channel.close();
        } catch (IOException e) {
            logger.debug("Closing the Docker stream failed: {}", e.toString());
        }
    }
}
