package com.gaskony.scriptide.gateway.exec;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import org.python.core.PyException;
import org.python.core.PyFrame;
import org.python.core.PyTraceback;

/**
 * Turns a failed execution into frames the editor can make clickable.
 *
 * <h2>Structurally, never by regex</h2>
 *
 * <p>The rendered traceback text is for humans. Parsing it back breaks on
 * non-ASCII paths and on nested exceptions, and it is the approach everyone
 * reaches for first. {@link PyTraceback} is a linked list of frames with the
 * filename, function and line already separated — walk that instead.</p>
 *
 * <h2>Which accessor, and why it depends on the call style</h2>
 *
 * <p>{@code ScriptManager.runCode} wraps failures in a {@code JythonExecException}
 * whose {@code getPyCause()} yields the {@link PyException}. This module does not
 * use that path — it calls {@code Py.runCode} directly (see
 * {@link PrivateStateRunner}), which throws the {@link PyException} itself. So the
 * traceback is read straight off the exception. Verified in spike S1.</p>
 *
 * <h2>Frame filenames</h2>
 *
 * <p>The submitted {@code fileName} appears verbatim in the top frame, so a
 * reversible token maps a frame back to its editor tab. A frame inside a project
 * library module is spelled {@code <module:dotted.name>} — measured, and the
 * reason a library frame can be made clickable at all.</p>
 */
public final class TracebackFormatter {

    /** Prefix Ignition gives a frame inside a project library module. */
    static final String LIBRARY_FRAME_PREFIX = "<module:";

    /** Guard against a pathological or cyclic traceback chain. */
    private static final int MAX_FRAMES = 50;

    private TracebackFormatter() { /* utility */ }

    /**
     * Describe a failure as JSON: the exception type, its message, and the frames.
     *
     * @param failure   what the execution threw
     * @param fileName  the token the source was submitted under, so frames
     *                  belonging to the edited document can be flagged
     * @param lineOffset number of lines prepended to the submitted source (for a
     *                  selection run) — subtracted so reported lines match the
     *                  editor
     */
    public static JsonObject describe(Throwable failure, String fileName, int lineOffset) {
        JsonObject out = new JsonObject();
        if (failure == null) {
            return out;
        }

        PyException py = findPyException(failure);
        if (py == null) {
            // A Java-level failure with no Python frames — still report it rather
            // than showing the user a blank Problems panel.
            out.addProperty("type", failure.getClass().getSimpleName());
            out.addProperty("message", String.valueOf(failure.getMessage()));
            out.add("frames", new JsonArray());
            return out;
        }

        out.addProperty("type", typeName(py));
        out.addProperty("message", messageOf(py));
        out.addProperty("rendered", safeToString(py));

        JsonArray frames = new JsonArray();
        PyTraceback tb = py.traceback;
        int guard = 0;
        while (tb != null && guard++ < MAX_FRAMES) {
            JsonObject frame = new JsonObject();
            String file = null;
            String function = null;
            PyFrame f = tb.tb_frame;
            if (f != null && f.f_code != null) {
                file = f.f_code.co_filename;
                function = f.f_code.co_name;
            }
            frame.addProperty("file", file);
            frame.addProperty("function", function);
            frame.addProperty("line", Math.max(1, tb.tb_lineno - lineOffset));
            // Tell the client what it can navigate to, rather than making it
            // re-derive the same string rules.
            frame.addProperty("isSubmitted", fileName != null && fileName.equals(file));
            frame.addProperty("libraryModule", libraryModuleOf(file));
            frames.add(frame);
            tb = (tb.tb_next instanceof PyTraceback next) ? next : null;
        }
        out.add("frames", frames);
        return out;
    }

    /**
     * The dotted module name of a project-library frame, or null.
     *
     * <p>{@code <module:util.helpers>} → {@code util.helpers}, which maps back to
     * the resource {@code ignition/script-python/util/helpers}.</p>
     */
    static String libraryModuleOf(String coFilename) {
        if (coFilename == null
            || !coFilename.startsWith(LIBRARY_FRAME_PREFIX)
            || !coFilename.endsWith(">")) {
            return null;
        }
        String inner = coFilename.substring(LIBRARY_FRAME_PREFIX.length(), coFilename.length() - 1);
        return inner.isBlank() ? null : inner;
    }

    /** The first PyException in the cause chain, if any. */
    private static PyException findPyException(Throwable t) {
        for (Throwable c = t; c != null; c = c.getCause()) {
            if (c instanceof PyException py) {
                return py;
            }
            if (c.getCause() == c) {
                break;
            }
        }
        return null;
    }

    private static String typeName(PyException py) {
        try {
            if (py.type != null) {
                Object name = py.type.__findattr__("__name__");
                if (name != null) {
                    return name.toString();
                }
                return py.type.toString();
            }
        } catch (RuntimeException e) {
            // Deliberately quiet: a broken exception type must not replace the
            // user's error with one of ours.
        }
        return "Error";
    }

    private static String messageOf(PyException py) {
        try {
            return py.value == null ? "" : py.value.toString();
        } catch (RuntimeException e) {
            return "";
        }
    }

    private static String safeToString(PyException py) {
        try {
            return py.toString();
        } catch (RuntimeException e) {
            return "";
        }
    }
}
