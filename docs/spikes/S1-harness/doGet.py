def doGet(request, session):
    """Script IDE S1 spike. Everything is nested: a WebDev python-resource silently
    returns an empty 200 if anything at all precedes the def. ?q=<check>, default env."""
    import json
    import sys
    import time
    import traceback

    PROJECT = "_ScriptIDE_Spike_"

    def jclass(o):
        try:
            return str(o.getClass().getName())
        except:
            return str(type(o))

    def gwctx():
        from com.inductiveautomation.ignition.gateway import IgnitionGateway
        return IgnitionGateway.get()

    def projman():
        return gwctx().getProjectManager()

    def psm():
        return projman().getProjectScriptManager(PROJECT)

    def safe(fn):
        try:
            return {"ok": True, "result": fn()}
        except:
            et, ev, tb = sys.exc_info()
            return {"ok": False,
                    "error": "%s: %s" % (jclass(ev) if ev is not None else str(et), str(ev)),
                    "trace": traceback.format_exc()}

    # ---------- Q0: environment ----------
    def q_env():
        from java.lang import System as JSystem
        c = gwctx()
        return {
            "jython_sys_version": str(sys.version),
            "java_version": str(JSystem.getProperty("java.version")),
            "gateway_class": jclass(c),
            "projects": sorted([str(n) for n in projman().getNames()]),
            "project_script_manager_class": jclass(psm()),
            "gateway_script_manager_class": jclass(c.getScriptManager()),
            "same_instance_as_gateway": psm() is c.getScriptManager(),
        }

    # ---------- Q4: ParserFacade on Python 2 syntax ----------
    def q_parser():
        from org.python.core import ParserFacade, CompilerFlags
        from java.io import StringReader
        samples = [
            ("py2_print_stmt", 'print "hello"\n'),
            ("py2_except_comma", 'try:\n    pass\nexcept ValueError, e:\n    pass\n'),
            ("py2_long_literal", 'x = 10L\n'),
            ("py2_backtick", 'x = `1`\n'),
            ("py2_exec_stmt", 'exec "x=1"\n'),
            ("py2_octal", 'x = 0777\n'),
            ("py2_ne_operator", 'x = 1 <> 2\n'),
            ("py2_raise_comma", 'raise ValueError, "msg"\n'),
            ("py3_print_call", 'print("hello")\n'),
            ("py3_only_fstring", 'x = f"{1}"\n'),
            ("syntax_error", 'def f(:\n    pass\n'),
            ("syntax_error_line3", 'a = 1\nb = 2\nc = = 3\n'),
        ]
        out = {}
        for name, src in samples:
            entry = {}
            try:
                mod = ParserFacade.parseExpressionOrModule(
                    StringReader(src), "<spike:%s>" % name, CompilerFlags())
                entry["parsed"] = True
                entry["ast_class"] = jclass(mod)
            except:
                et, ev, tb = sys.exc_info()
                entry["parsed"] = False
                entry["exc_class"] = jclass(ev) if ev is not None else str(et)
                entry["message"] = str(ev)
                # probe every plausible position carrier
                for attr in ("line", "charPositionInLine", "lineno", "offset", "col_offset"):
                    try:
                        entry["attr_" + attr] = str(getattr(ev, attr))
                    except:
                        pass
                # PyException carrying a SyntaxError has .value as a tuple
                try:
                    entry["py_value_repr"] = repr(ev.value)
                except:
                    pass
                try:
                    entry["py_type"] = str(ev.type)
                except:
                    pass
            out[name] = entry
        return out

    # ---------- Q5: hints tree, gateway vs project ----------
    def q_hints():
        c = gwctx()

        def roots(tree):
            return sorted([str(k) for k in tree.children().keySet()])

        def walk_count(node, depth):
            if depth > 12:
                return 0
            n = 1
            for child in node.children().values():
                n += walk_count(child, depth + 1)
            return n

        gtree = c.getScriptManager().getHintsTree()
        ptree = psm().getHintsTree()

        def sample_method(tree, path):
            node = tree
            for seg in path.split("."):
                node = node.children().get(seg)
                if node is None:
                    return {"found": False, "missing_at": seg}
            methods = node.methods()
            if methods is None or methods.isEmpty():
                return {"found": True, "method_count": 0}
            m = methods.get(0)
            params = []
            try:
                for p in m.getParameters():
                    params.append({"name": str(p.getName()),
                                   "optional": bool(p.getOptional()),
                                   "default": str(p.getDefault()),
                                   "desc_len": len(str(p.getDescription() or ""))})
            except:
                params.append({"param_extraction_failed": traceback.format_exc()})
            return {
                "found": True,
                "method_count": methods.size(),
                "first_method": str(m.getName()),
                "description_len": len(str(m.getDescription() or "")),
                "return_type": str(m.getReturnType()),
                "parameters": params,
                "all_method_names": sorted([str(x.getName()) for x in methods])[:40],
            }

        return {
            "gateway_roots": roots(gtree),
            "project_roots": roots(ptree),
            "roots_differ": roots(gtree) != roots(ptree),
            "gateway_node_count": walk_count(gtree, 0),
            "project_node_count": walk_count(ptree, 0),
            "project_has_spikelib": "spikelib" in roots(ptree),
            "sample_system_tag": sample_method(ptree, "system.tag"),
            "sample_spikelib": sample_method(ptree, "spikelib"),
        }

    # ---------- Q2: per-thread stdout routing ----------
    def q_routing():
        from java.io import OutputStream
        from java.lang import Thread, Runnable

        class Router(OutputStream):
            def __init__(self):
                self.sinks = {}
                self.unrouted = [0]

            def write(self, *a):
                try:
                    tid = Thread.currentThread().getId()
                    sink = self.sinks.get(tid)
                    if sink is None:
                        self.unrouted[0] += 1
                        return
                    if len(a) == 1:
                        b = a[0]
                        if isinstance(b, int):
                            sink.append(chr(b & 0xFF))
                        else:
                            sink.append("".join([chr(x & 0xFF) for x in b]))
                    else:
                        b, off, ln = a
                        sink.append("".join([chr(b[i] & 0xFF) for i in range(off, off + ln)]))
                except:
                    pass  # a substream of the platform's stdout must never throw

        sm = psm()
        router = Router()
        results = {}
        errors = {}

        class Worker(Runnable):
            def __init__(self, tag, n):
                self.tag = tag
                self.n = n

            def run(self):
                tid = Thread.currentThread().getId()
                router.sinks[tid] = []
                try:
                    code = ('for i in range(%d):\n'
                            '    print "%s-%%04d" %% i\n') % (self.n, self.tag)
                    sm.runCode(code, sm.createLocalsMap(), "<spike-%s>" % self.tag)
                    sm.runCode("import sys\nsys.stdout.flush()\n",
                               sm.createLocalsMap(), "<spike-flush>")
                except:
                    errors[self.tag] = traceback.format_exc()
                results[self.tag] = "".join(router.sinks.pop(tid, []))

        sm.addStdOutStream(router)
        try:
            n = 500
            threads = []
            for tag in ("AAA", "BBB"):
                t = Thread(Worker(tag, n))
                t.setName("spike-" + tag)
                threads.append(t)
            for t in threads:
                t.start()
            for t in threads:
                t.join(30000)
        finally:
            sm.removeStdOutStream(router)

        report = {"errors": errors, "unrouted_writes": router.unrouted[0],
                  "expected_lines_each": 500}
        for tag in ("AAA", "BBB"):
            text = results.get(tag, "")
            lines = [l for l in text.split("\n") if l.strip()]
            other = "BBB" if tag == "AAA" else "AAA"
            report[tag] = {
                "chars": len(text),
                "lines": len(lines),
                "own_lines": len([l for l in lines if l.startswith(tag + "-")]),
                "CROSSTALK_lines": len([l for l in lines if l.startswith(other + "-")]),
                "first": lines[0] if lines else None,
                "last": lines[-1] if lines else None,
                "missing": 500 - len([l for l in lines if l.startswith(tag + "-")]),
            }
        return report

    # ---------- Q2b: FALLBACK A - private PySystemState per execution ----------
    def q_routing2():
        from org.python.core import Py, CompileMode, CompilerFlags
        from com.inductiveautomation.ignition.common.script import ScriptManager
        from java.io import ByteArrayOutputStream
        from java.lang import Thread, Runnable

        sm = psm()
        glob = sm.getGlobals()
        results = {}
        errors = {}

        def run_private(source, filename, locals_map):
            """Bypass ScriptManager.runCode: give THIS thread its own PySystemState so
            sys.stdout is genuinely private. Returns (stdout, stderr, error_or_None)."""
            out = ByteArrayOutputStream()
            err = ByteArrayOutputStream()
            prev = None
            try:
                prev = Py.getSystemState()
            except:
                pass
            state = ScriptManager.createUtf8PySystemState(out, err)
            failure = None
            try:
                Py.setSystemState(state)
                code = Py.compile_flags(source, filename, CompileMode.exec, CompilerFlags())
                Py.runCode(code, locals_map, glob)
            except:
                et, ev, tb = sys.exc_info()
                failure = {"class": jclass(ev) if ev is not None else str(et),
                           "str": str(ev)[:600]}
            finally:
                try:
                    sysmod = state.modules.get("sys") if state.modules is not None else None
                except:
                    sysmod = None
                try:
                    Py.runCode(Py.compile_flags(
                        "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n",
                        "<flush>", CompileMode.exec, CompilerFlags()),
                        locals_map, glob)
                except:
                    pass
                if prev is not None:
                    try:
                        Py.setSystemState(prev)
                    except:
                        pass
            return (str(out.toString("UTF-8")), str(err.toString("UTF-8")), failure)

        class Worker(Runnable):
            def __init__(self, tag, n):
                self.tag = tag
                self.n = n

            def run(self):
                try:
                    src = ('for i in range(%d):\n'
                           '    print "%s-%%04d" %% i\n') % (self.n, self.tag)
                    o, e, f = run_private(src, "<spike2-%s>" % self.tag,
                                          sm.createLocalsMap())
                    results[self.tag] = {"out": o, "err": e, "failure": f}
                except:
                    errors[self.tag] = traceback.format_exc()

        n = 500
        threads = []
        for tag in ("AAA", "BBB"):
            t = Thread(Worker(tag, n))
            t.setName("spike2-" + tag)
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(60000)

        report = {"errors": errors, "expected_lines_each": n}
        for tag in ("AAA", "BBB"):
            entry = results.get(tag) or {}
            text = entry.get("out", "")
            lines = [l for l in text.split("\n") if l.strip()]
            other = "BBB" if tag == "AAA" else "AAA"
            report[tag] = {
                "failure": entry.get("failure"),
                "stderr_len": len(entry.get("err", "")),
                "lines": len(lines),
                "own_lines": len([l for l in lines if l.startswith(tag + "-")]),
                "CROSSTALK_lines": len([l for l in lines if l.startswith(other + "-")]),
                "missing": n - len([l for l in lines if l.startswith(tag + "-")]),
                "first": lines[0] if lines else None,
                "last": lines[-1] if lines else None,
            }

        # does system.* still resolve under a private PySystemState?
        o1, e1, f1 = run_private(
            "import system\nprint 'tz=' + str(system.date.now())[:4]\n",
            "<spike2-system>", sm.createLocalsMap())
        report["system_call"] = {"stdout": o1.strip()[:200], "stderr": e1.strip()[:300],
                                 "failure": f1}

        # does the PROJECT LIBRARY still import under a private PySystemState,
        # and does a traceback still carry the <module:...> frame?
        o2, e2, f2 = run_private(
            "import spikelib\nspikelib.level2()\n",
            "<script-ide:%s:console>" % PROJECT, sm.createLocalsMap())
        report["project_library"] = {"stdout": o2.strip()[:200],
                                     "stderr_tail": e2.strip()[-600:],
                                     "failure": f2}
        return report

    # ---------- Q2c: FALLBACK A+ - private state that SHARES the manager's modules ----------
    def q_routing3():
        from org.python.core import Py, CompileMode, CompilerFlags
        from com.inductiveautomation.ignition.common.script import ScriptManager
        from java.io import ByteArrayOutputStream
        from java.lang import Thread, Runnable

        sm = psm()
        glob = sm.getGlobals()
        probe = {}

        def manager_state():
            """ScriptManager.runCode() calls setState() -> Py.setSystemState(manager.sys)
            on the CALLING thread and does not restore it, so after any runCode the
            thread's system state IS the manager's. No reflection needed."""
            sm.runCode("pass\n", sm.createLocalsMap(), "<probe>")
            return Py.getSystemState()

        mgr = manager_state()
        probe["manager_state_class"] = jclass(mgr)
        try:
            probe["manager_modules_has_system"] = bool(mgr.modules.__finditem__("system") is not None)
        except:
            probe["manager_modules_probe_error"] = traceback.format_exc()
        try:
            probe["manager_modules_has_spikelib"] = bool(mgr.modules.__finditem__("spikelib") is not None)
        except:
            pass

        def run_private(source, filename, locals_map):
            out = ByteArrayOutputStream()
            err = ByteArrayOutputStream()
            state = ScriptManager.createUtf8PySystemState(out, err)
            # share the manager's live module registry and import path
            state.modules = mgr.modules
            state.path = mgr.path
            failure = None
            prev = Py.getSystemState()
            try:
                Py.setSystemState(state)
                code = Py.compile_flags(source, filename, CompileMode.exec, CompilerFlags())
                Py.runCode(code, locals_map, glob)
            except:
                et, ev, tb = sys.exc_info()
                failure = {"class": jclass(ev) if ev is not None else str(et),
                           "str": str(ev)[:400]}
                # structured traceback under the private state
                try:
                    opt = ev.getPyCause()
                    if opt.isPresent():
                        pyexc = opt.get()
                        frames = []
                        tbn = pyexc.traceback
                        g = 0
                        while tbn is not None and g < 30:
                            g += 1
                            frames.append({
                                "co_filename": str(tbn.tb_frame.f_code.co_filename),
                                "co_name": str(tbn.tb_frame.f_code.co_name),
                                "tb_lineno": int(tbn.tb_lineno)})
                            tbn = tbn.tb_next
                        failure["frames"] = frames
                        failure["rendered"] = str(pyexc)[:600]
                except:
                    try:
                        failure["frames_via_pyexception"] = [{
                            "co_filename": str(ev.traceback.tb_frame.f_code.co_filename),
                            "tb_lineno": int(ev.traceback.tb_lineno)}]
                        failure["rendered"] = str(ev)[:600]
                    except:
                        failure["frame_error"] = traceback.format_exc()[:600]
            finally:
                try:
                    Py.runCode(Py.compile_flags(
                        "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n",
                        "<flush>", CompileMode.exec, CompilerFlags()), locals_map, glob)
                except:
                    pass
                try:
                    Py.setSystemState(prev)
                except:
                    pass
            return (str(out.toString("UTF-8")), str(err.toString("UTF-8")), failure)

        results = {}
        errors = {}

        class Worker(Runnable):
            def __init__(self, tag, n):
                self.tag = tag
                self.n = n

            def run(self):
                try:
                    src = ('import system\n'
                           'for i in range(%d):\n'
                           '    print "%s-%%04d" %% i\n') % (self.n, self.tag)
                    o, e, f = run_private(src, "<spike3-%s>" % self.tag,
                                          sm.createLocalsMap())
                    results[self.tag] = {"out": o, "err": e, "failure": f}
                except:
                    errors[self.tag] = traceback.format_exc()

        n = 500
        threads = []
        for tag in ("AAA", "BBB"):
            t = Thread(Worker(tag, n))
            t.setName("spike3-" + tag)
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(60000)

        report = {"probe": probe, "errors": errors, "expected_lines_each": n}
        for tag in ("AAA", "BBB"):
            entry = results.get(tag) or {}
            text = entry.get("out", "")
            lines = [l for l in text.split("\n") if l.strip()]
            other = "BBB" if tag == "AAA" else "AAA"
            report[tag] = {
                "failure": entry.get("failure"),
                "lines": len(lines),
                "own_lines": len([l for l in lines if l.startswith(tag + "-")]),
                "CROSSTALK_lines": len([l for l in lines if l.startswith(other + "-")]),
                "missing": n - len([l for l in lines if l.startswith(tag + "-")]),
            }

        o1, e1, f1 = run_private(
            "import system\nprint 'now=' + str(system.date.now())[:4]\n",
            "<spike3-system>", sm.createLocalsMap())
        report["system_call"] = {"stdout": o1.strip()[:200], "stderr": e1.strip()[:400],
                                 "failure": f1}

        o2, e2, f2 = run_private(
            "import spikelib\nspikelib.level2()\n",
            "<script-ide:%s:console>" % PROJECT, sm.createLocalsMap())
        report["project_library_traceback"] = {"stdout": o2.strip()[:200],
                                               "stderr_tail": e2.strip()[-400:],
                                               "failure": f2}

        o3, e3, f3 = run_private(
            "import sys\nprint 'to stdout'\nsys.stderr.write('to stderr\\n')\n",
            "<spike3-streams>", sm.createLocalsMap())
        report["stream_split"] = {"stdout": o3.strip()[:200], "stderr": e3.strip()[:200],
                                  "failure": f3}
        return report

    # ---------- FINAL: private modules map + own sys + exc_info traceback + interrupt ----------
    def q_final():
        from org.python.core import Py, CompileMode, CompilerFlags, PySystemState
        from com.inductiveautomation.ignition.common.script import ScriptManager
        from java.io import ByteArrayOutputStream
        from java.lang import Thread, Runnable

        sm = psm()
        glob = sm.getGlobals()

        sm.runCode("pass\n", sm.createLocalsMap(), "<probe>")
        mgr = Py.getSystemState()

        def run_private(source, filename, locals_map):
            """Private stdout AND stderr: copy the manager's module registry so the
            platform API imports, then point the copy's 'sys' at OUR state so an
            explicit sys.stdout/sys.stderr write is isolated too."""
            out = ByteArrayOutputStream()
            err = ByteArrayOutputStream()
            state = ScriptManager.createUtf8PySystemState(out, err)
            try:
                state.modules = mgr.modules.copy()
                state.modules.__setitem__("sys", state)
            except:
                state.modules = mgr.modules
            state.path = mgr.path
            failure = None
            prev = Py.getSystemState()
            tid = Thread.currentThread().getId()
            try:
                Py.setSystemState(state)
                code = Py.compile_flags(source, filename, CompileMode.exec, CompilerFlags())
                Py.runCode(code, locals_map, glob)
            except:
                et, ev, tb = sys.exc_info()
                failure = {"class": str(et), "str": str(ev)[:400], "frames": []}
                g = 0
                while tb is not None and g < 30:
                    g += 1
                    try:
                        failure["frames"].append({
                            "co_filename": str(tb.tb_frame.f_code.co_filename),
                            "co_name": str(tb.tb_frame.f_code.co_name),
                            "tb_lineno": int(tb.tb_lineno)})
                    except:
                        failure["frames"].append({"err": traceback.format_exc()[:200]})
                    tb = tb.tb_next
            finally:
                try:
                    Py.runCode(Py.compile_flags(
                        "import sys\nsys.stdout.flush()\nsys.stderr.flush()\n",
                        "<flush>", CompileMode.exec, CompilerFlags()), locals_map, glob)
                except:
                    pass
                try:
                    Py.setSystemState(prev)
                except:
                    pass
            return {"tid": tid,
                    "stdout": str(out.toString("UTF-8")),
                    "stderr": str(err.toString("UTF-8")),
                    "failure": failure}

        report = {}

        # 1. explicit sys.stdout / sys.stderr writes must now be isolated
        r = run_private("import sys\n"
                        "print 'via print'\n"
                        "sys.stdout.write('via sys.stdout\\n')\n"
                        "sys.stderr.write('via sys.stderr\\n')\n",
                        "<final-streams>", sm.createLocalsMap())
        report["streams"] = {"stdout": r["stdout"].strip(), "stderr": r["stderr"].strip(),
                             "failure": r["failure"]}

        # 2. platform API still imports through the COPIED registry
        r = run_private("import system\nprint 'v=' + str(system.util.getSystemFlags())\n",
                        "<final-system>", sm.createLocalsMap())
        report["system_call"] = {"stdout": r["stdout"].strip()[:120],
                                 "failure": r["failure"]}

        # 3. project library imports, and the traceback keeps <module:...> frames
        r = run_private("import spikelib\nspikelib.level2()\n",
                        "<script-ide:%s:console>" % PROJECT, sm.createLocalsMap())
        report["library_traceback"] = r["failure"]

        # 4. an uncaught traceback must NOT leak to the platform stderr
        report["traceback_went_to_private_stderr"] = len(r["stderr"]) > 0

        # 5. does ScriptManager.interrupt() still reach a Py.runCode execution?
        state_box = {}

        class Busy(Runnable):
            def run(self):
                state_box["tid"] = Thread.currentThread().getId()
                t0 = time.time()
                res = run_private(
                    "import time\nend = time.time() + 15\nwhile time.time() < end:\n    pass\n",
                    "<final-busy>", sm.createLocalsMap())
                state_box["elapsed_s"] = round(time.time() - t0, 2)
                state_box["failure"] = res["failure"]

        t = Thread(Busy())
        t.setName("final-busy")
        t.start()
        time.sleep(3.0)
        tid = state_box.get("tid")
        try:
            ScriptManager.interrupt(tid)
            state_box["interrupt_called_on"] = tid
        except:
            state_box["interrupt_error"] = traceback.format_exc()[:400]
        t.join(20000)
        state_box["still_alive"] = t.isAlive()
        report["interrupt_busy_loop"] = state_box
        report["_reading"] = ("elapsed ~3s => interrupt reaches a Py.runCode execution. "
                              "elapsed ~15s => it does not, and Stop needs another mechanism.")
        return report

    # ---------- STOP: does interrupt reach Py.runCode, and what does it raise? ----------
    def q_stop():
        from org.python.core import Py, CompileMode, CompilerFlags
        from com.inductiveautomation.ignition.common.script import ScriptManager
        from java.io import ByteArrayOutputStream
        from java.lang import Thread, Runnable, Throwable

        sm = psm()
        glob = sm.getGlobals()
        sm.runCode("pass\n", sm.createLocalsMap(), "<probe>")
        mgr = Py.getSystemState()

        def run_private(source, filename):
            out = ByteArrayOutputStream()
            err = ByteArrayOutputStream()
            state = ScriptManager.createUtf8PySystemState(out, err)
            try:
                state.modules = mgr.modules.copy()
                state.modules.__setitem__("sys", state)
            except:
                state.modules = mgr.modules
            state.path = mgr.path
            prev = Py.getSystemState()
            outcome = {}
            try:
                Py.setSystemState(state)
                code = Py.compile_flags(source, filename, CompileMode.exec, CompilerFlags())
                Py.runCode(code, sm.createLocalsMap(), glob)
                outcome["result"] = "completed normally"
            except Throwable, t:
                # a Java Error (e.g. ScriptCanceledError) is NOT caught by a bare
                # `except:` in Jython -- this clause is the one that matters for Stop
                outcome["result"] = "java throwable"
                outcome["java_class"] = jclass(t)
                outcome["java_str"] = str(t)[:300]
            except:
                et, ev, tb = sys.exc_info()
                outcome["result"] = "python exception"
                outcome["py_class"] = str(et)
                outcome["py_str"] = str(ev)[:300]
            finally:
                try:
                    Py.setSystemState(prev)
                except:
                    pass
            outcome["stdout_tail"] = str(out.toString("UTF-8"))[-120:]
            return outcome

        def trial(label, source, interrupt_after, join_ms):
            box = {"label": label}

            class W(Runnable):
                def run(self):
                    box["tid"] = Thread.currentThread().getId()
                    t0 = time.time()
                    try:
                        box["outcome"] = run_private(source, "<stop-%s>" % label)
                    except Throwable, t:
                        box["outcome"] = {"escaped_java": jclass(t)}
                    except:
                        box["outcome"] = {"escaped_py": traceback.format_exc()[:300]}
                    box["elapsed_s"] = round(time.time() - t0, 2)

            t = Thread(W())
            t.setName("stop-" + label)
            t0 = time.time()
            t.start()
            time.sleep(interrupt_after)
            box["interrupt_at_s"] = interrupt_after
            tid = box.get("tid")
            if tid is not None:
                try:
                    ScriptManager.interrupt(tid)
                    box["interrupt_call"] = "returned"
                except:
                    box["interrupt_call"] = traceback.format_exc()[:300]
            t.join(join_ms)
            # measured by the CALLER: the worker thread can be killed outright by a
            # Java Error that escapes Jython's except machinery, so it cannot time itself
            box["wallclock_total_s"] = round(time.time() - t0, 2)
            box["still_alive_after_join"] = t.isAlive()
            return box

        return {
            "busy_loop_15s": trial(
                "busy",
                "import time\nend = time.time() + 15\n"
                "while time.time() < end:\n    pass\nprint 'FINISHED NORMALLY'\n",
                3.0, 25000),
            "java_sleep_10s": trial(
                "sleep",
                "import time\ntime.sleep(10)\nprint 'FINISHED NORMALLY'\n",
                2.0, 20000),
            "_reading": ("busy elapsed ~3s => Stop works at Python trace points. "
                         "sleep elapsed ~10s => a script blocked in a Java call cannot "
                         "be stopped, so the UI must say Stop is best-effort."),
        }

    # ---------- Q3: interrupt ----------
    def q_interrupt():
        from com.inductiveautomation.ignition.common.script import ScriptManager
        from java.lang import Thread, Runnable

        sm = psm()

        def run_and_interrupt(label, code, interrupt_after, join_ms):
            state = {}

            class W(Runnable):
                def run(self):
                    state["tid"] = Thread.currentThread().getId()
                    t0 = time.time()
                    try:
                        sm.runCode(code, sm.createLocalsMap(), "<spike-%s>" % label)
                        state["outcome"] = "completed normally"
                    except:
                        et, ev, tb = sys.exc_info()
                        state["outcome"] = "raised %s: %s" % (
                            jclass(ev) if ev is not None else str(et), str(ev)[:300])
                    state["elapsed_s"] = round(time.time() - t0, 2)

            t = Thread(W())
            t.setName("spike-" + label)
            t.start()
            time.sleep(interrupt_after)
            tid = state.get("tid")
            state["interrupt_called_on_tid"] = tid
            if tid is not None:
                try:
                    ScriptManager.interrupt(tid)
                    state["interrupt_returned"] = True
                except:
                    state["interrupt_error"] = traceback.format_exc()
            t.join(join_ms)
            state["thread_alive_after_join"] = t.isAlive()
            state["interrupt_at_s"] = interrupt_after
            return state

        return {
            "busy_loop": run_and_interrupt(
                "busy",
                "import time\nend = time.time() + 15\nwhile time.time() < end:\n    pass\n",
                3.0, 20000),
            "java_blocked_sleep": run_and_interrupt(
                "sleep",
                "import time\ntime.sleep(10)\n",
                2.0, 15000),
            "_note": ("busy_loop elapsed ~3s => interrupt works at trace points. "
                      "java_blocked_sleep elapsed ~10s => a script blocked in a Java "
                      "call cannot be stopped, which the plan predicted."),
        }

    # ---------- Q6: traceback walk ----------
    def q_traceback():
        sm = psm()
        FILENAME = "<script-ide:%s:ignition/script-python/Spike/Console>" % PROJECT
        code = "import spikelib\nspikelib.level2()\n"
        out = {"submitted_filename": FILENAME}
        try:
            sm.runCode(code, sm.createLocalsMap(), FILENAME)
            out["unexpected"] = "code did not raise"
            return out
        except:
            et, ev, tb = sys.exc_info()

        out["exc_class"] = jclass(ev) if ev is not None else str(et)
        out["exc_str"] = str(ev)[:500]

        pyexc = None
        try:
            opt = ev.getPyCause()
            out["getPyCause_present"] = bool(opt.isPresent())
            if opt.isPresent():
                pyexc = opt.get()
        except:
            out["getPyCause_error"] = traceback.format_exc()

        if pyexc is None:
            return out

        out["pyexc_class"] = jclass(pyexc)
        try:
            out["pyexc_type"] = str(pyexc.type)
            out["pyexc_value"] = str(pyexc.value)
        except:
            pass

        frames = []
        try:
            tbn = pyexc.traceback
            guard = 0
            while tbn is not None and guard < 50:
                guard += 1
                frame = {}
                try:
                    frame["tb_lineno"] = int(tbn.tb_lineno)
                except:
                    frame["tb_lineno"] = None
                try:
                    code_obj = tbn.tb_frame.f_code
                    frame["co_filename"] = str(code_obj.co_filename)
                    frame["co_name"] = str(code_obj.co_name)
                except:
                    frame["frame_error"] = traceback.format_exc()
                frames.append(frame)
                tbn = tbn.tb_next
        except:
            out["walk_error"] = traceback.format_exc()

        out["frames"] = frames
        out["rendered"] = str(pyexc)[:1500]
        return out

    # ---------- dispatch ----------
    checks = {
        "env": q_env,
        "parser": q_parser,
        "hints": q_hints,
        "routing": q_routing,
        "routing2": q_routing2,
        "routing3": q_routing3,
        "final": q_final,
        "stop": q_stop,
        "interrupt": q_interrupt,
        "traceback": q_traceback,
    }

    params = request.get("params") or {}
    q = str(params.get("q", "env"))
    body = {"query": q, "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if q == "all":
        names = ["env", "parser", "hints", "routing", "traceback"]
    elif q in checks:
        names = [q]
    else:
        body["error"] = "unknown check"
        body["available"] = sorted(checks.keys()) + ["all"]
        return {"json": json.dumps(body, indent=2, sort_keys=True)}

    for name in names:
        body[name] = safe(checks[name])

    return {"json": json.dumps(body, indent=2, sort_keys=True)}
