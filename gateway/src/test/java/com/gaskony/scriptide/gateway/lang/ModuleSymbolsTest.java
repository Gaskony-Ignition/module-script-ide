package com.gaskony.scriptide.gateway.lang;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Parsing real Ignition code.
 *
 * <p>The Python-2 cases are the point of the whole approach: no maintained
 * third-party Python parser handles them, which is why this uses Jython's own.</p>
 */
class ModuleSymbolsTest {

    @ParameterizedTest(name = "parses Python 2 syntax: {0}")
    @ValueSource(strings = {
        "print 'hello'\n",
        "try:\n\tpass\nexcept ValueError, e:\n\tpass\n",
        "x = 10L\n",
        "x = `1`\n",
        "exec 'x=1'\n",
        "x = 0777\n",
        "x = 1 <> 2\n",
        "raise ValueError, 'msg'\n",
    })
    @DisplayName("Python-2-only forms parse without error")
    void parsesPython2(String source) {
        // Every one of these is a syntax error to a Python 3 parser, and all of them
        // appear in real Ignition scripts.
        assertThat(ModuleSymbols.parse("m", source).syntaxError()).isEmpty();
    }

    @Test
    @DisplayName("a syntax error is reported once, with a 0-based line")
    void reportsSyntaxErrorPosition() {
        ModuleSymbols m = ModuleSymbols.parse("m", "a = 1\nb = 2\nc = = 3\n");
        assertThat(m.syntaxError()).isPresent();
        // Third line, 0-based => 2. An off-by-one here puts the squiggle on the
        // wrong line, which reads as an editor bug.
        assertThat(m.errorLine()).isEqualTo(2);
    }

    @Test
    @DisplayName("a module that does not parse still returns, rather than throwing")
    void badModuleDoesNotThrow() {
        // One broken script must not take out the whole project index — and a
        // half-typed script is the normal case, not an edge case.
        ModuleSymbols m = ModuleSymbols.parse("broken", "def f(:\n");
        assertThat(m.syntaxError()).isPresent();
        assertThat(m.symbols()).isEmpty();
    }

    @Test
    @DisplayName("functions, classes, methods and module variables are indexed")
    void indexesDefinitions() {
        ModuleSymbols m = ModuleSymbols.parse("m",
            "CONSTANT = 3\n"
                + "\n"
                + "def compute(a, b=2, *rest, **kw):\n"
                + "\t'''Adds things.'''\n"
                + "\treturn a + b\n"
                + "\n"
                + "class Widget:\n"
                + "\tdef spin(self):\n"
                + "\t\tpass\n");

        assertThat(m.symbols()).extracting(ModuleSymbols.Symbol::name)
            .contains("CONSTANT", "compute", "Widget", "spin");

        var compute = m.find("compute").orElseThrow();
        assertThat(compute.kind()).isEqualTo(ModuleSymbols.SymbolKind.FUNCTION);
        assertThat(compute.signature()).isEqualTo("compute(a, b=..., *rest, **kw)");
        assertThat(compute.documentation()).contains("Adds things");
        assertThat(compute.line()).isEqualTo(2);   // 0-based

        var spin = m.symbols().stream().filter(s -> s.name().equals("spin")).findFirst()
            .orElseThrow();
        assertThat(spin.kind()).isEqualTo(ModuleSymbols.SymbolKind.METHOD);
        assertThat(spin.container()).isEqualTo("Widget");
    }

    @Test
    @DisplayName("a nested function is NOT indexed, because nothing can import it")
    void skipsNestedFunctions() {
        ModuleSymbols m = ModuleSymbols.parse("m",
            "def outer():\n\tdef inner():\n\t\tpass\n\treturn inner\n");
        assertThat(m.symbols()).extracting(ModuleSymbols.Symbol::name)
            .containsExactly("outer");
    }

    @Test
    @DisplayName("import forms bind the right names")
    void resolvesImportBindings() {
        ModuleSymbols m = ModuleSymbols.parse("m",
            "import system\n"
                + "import a.b.c\n"
                + "import x.y as z\n"
                + "from util import helper\n"
                + "from pkg import thing as other\n"
                + "from wild import *\n");

        assertThat(m.imports()).extracting(ModuleSymbols.ImportBinding::boundName)
            // `import a.b.c` binds `a`, NOT `a.b.c` — treating it as the full path
            // silently breaks resolution of everything under it.
            .contains("system", "a", "z", "helper", "other", "*");

        var dotted = m.imports().stream().filter(i -> i.boundName().equals("a")).findFirst()
            .orElseThrow();
        assertThat(dotted.targetModule()).isEqualTo("a.b.c");

        var star = m.imports().stream().filter(ModuleSymbols.ImportBinding::star).findFirst()
            .orElseThrow();
        // Recorded so undefined-name checking can disable itself for this module
        // rather than emit nonsense about names the star import provides.
        assertThat(star.targetModule()).isEqualTo("wild");
    }

    @Test
    @DisplayName("a script with no trailing newline parses — that is the normal case here")
    void parsesWithoutTrailingNewline() {
        ModuleSymbols m = ModuleSymbols.parse("m", "def f():\n\treturn 1");
        assertThat(m.syntaxError()).isEmpty();
        assertThat(m.find("f")).isPresent();
    }
}
