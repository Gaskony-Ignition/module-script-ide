package com.gaskony.scriptide.gateway.testing;

import com.gaskony.scriptide.gateway.lang.ModuleSymbols;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * What counts as a test, proved against real Jython parses.
 *
 * <p>Both halves of the convention are asserted, and the NEGATIVE half is the
 * one that matters: a discovery rule that is too generous puts
 * {@code test_connection} under a Run All button, and the failure mode is a
 * production side effect fired by someone exploring a new panel.</p>
 */
class TestDiscoveryTest {

    private static Map<String, ModuleSymbols> project(String... nameThenSource) {
        Map<String, ModuleSymbols> out = new LinkedHashMap<>();
        for (int i = 0; i < nameThenSource.length; i += 2) {
            out.put(nameThenSource[i],
                ModuleSymbols.parse(nameThenSource[i], nameThenSource[i + 1]));
        }
        return out;
    }

    // ==================== The module rule ====================

    @Test
    @DisplayName("a module whose last name starts with 'test' is a test module")
    void testPrefixedModule() {
        assertThat(TestDiscovery.isTestModule("orders.test_totals")).isTrue();
        assertThat(TestDiscovery.isTestModule("tests")).isTrue();
        assertThat(TestDiscovery.isTestModule("Test_Orders")).isTrue();
    }

    @Test
    @DisplayName("a module under a 'tests' package is a test module")
    void testsPackage() {
        assertThat(TestDiscovery.isTestModule("orders.tests.totals")).isTrue();
        assertThat(TestDiscovery.isTestModule("tests.totals")).isTrue();
    }

    @Test
    @DisplayName("an ordinary module is not, however its functions are named")
    void ordinaryModuleIsNot() {
        assertThat(TestDiscovery.isTestModule("plc.diagnostics")).isFalse();
        assertThat(TestDiscovery.isTestModule("orders.totals")).isFalse();
        assertThat(TestDiscovery.isTestModule("")).isFalse();
        assertThat(TestDiscovery.isTestModule(null)).isFalse();
    }

    @Test
    @DisplayName("'testing.utils' is a module ABOUT testing, and is not one")
    void testingIsNotTests() {
        // Matched exactly, not as a prefix: `testing` holds helpers, and treating
        // it as a package of tests would run them.
        assertThat(TestDiscovery.isTestModule("testing.utils")).isFalse();
    }

    // ==================== The function rule ====================

    @Test
    @DisplayName("test_ prefixed, or bare 'test'")
    void functionNames() {
        assertThat(TestDiscovery.isTestName("test_sums")).isTrue();
        assertThat(TestDiscovery.isTestName("test")).isTrue();
        assertThat(TestDiscovery.isTestName("testSums")).isFalse();
        assertThat(TestDiscovery.isTestName("check_sums")).isFalse();
        assertThat(TestDiscovery.isTestName(null)).isFalse();
    }

    // ==================== Discovery over real parses ====================

    @Test
    @DisplayName("finds top-level test functions and skips the helpers beside them")
    void findsTopLevelTests() {
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "orders.test_totals",
            "def helper():\n    return 1\n\ndef test_sums():\n    assert 1 == 1\n"));

        assertThat(found).hasSize(1);
        assertThat(found.get(0).tests()).extracting(TestDiscovery.TestCase::function)
            .containsExactly("test_sums");
    }

    @Test
    @DisplayName("a test's id is module.function, and its line is the def")
    void idAndLine() {
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "orders.test_totals", "\n\ndef test_sums():\n    pass\n"));

        TestDiscovery.TestCase test = found.get(0).tests().get(0);
        assertThat(test.id()).isEqualTo("orders.test_totals.test_sums");
        // 0-based, so the third line of the file is 2. Getting this wrong lands
        // click-to-open one line off, which reads as a bug in the editor.
        assertThat(test.line()).isEqualTo(2);
    }

    @Test
    @DisplayName("finds test methods on a Test-named class, and names them fully")
    void findsClassMethods() {
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "orders.test_totals",
            "class TestTotals:\n    def test_sums(self):\n        pass\n"));

        TestDiscovery.TestCase test = found.get(0).tests().get(0);
        assertThat(test.className()).isEqualTo("TestTotals");
        assertThat(test.id()).isEqualTo("orders.test_totals.TestTotals.test_sums");
    }

    @Test
    @DisplayName("ignores a test-named method on a class that is not a Test class")
    void ignoresNonTestClasses() {
        // A helper class in a test module can perfectly well have a `test_`
        // method; instantiating it with no arguments and calling that is not
        // something the runner should decide to do.
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "orders.test_totals",
            "class Fixture:\n    def test_sums(self):\n        pass\n"));
        assertThat(found).isEmpty();
    }

    @Test
    @DisplayName("a test-named function in an ORDINARY module is not discovered")
    void ordinaryModuleContributesNothing() {
        // The rule that keeps `plc.diagnostics.test_connection` off a Run All
        // button. It is the whole reason discovery is narrow.
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "plc.diagnostics", "def test_connection():\n    pass\n"));
        assertThat(found).isEmpty();
    }

    @Test
    @DisplayName("reports whether the module brackets its tests")
    void reportsSetUpAndTearDown() {
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "orders.test_totals",
            "def setUp():\n    pass\n\ndef test_a():\n    pass\n"));

        assertThat(found.get(0).hasSetUp()).isTrue();
        assertThat(found.get(0).hasTearDown()).isFalse();
        // setUp is not itself a test, however the module is named.
        assertThat(found.get(0).tests()).hasSize(1);
    }

    @Test
    @DisplayName("a module with no tests in it contributes no entry at all")
    void emptyTestModuleIsOmitted() {
        assertThat(TestDiscovery.discover(project(
            "orders.test_helpers", "def build_order():\n    return {}\n"))).isEmpty();
    }

    @Test
    @DisplayName("a module that does not parse contributes nothing")
    void unparseableModuleIsSkipped() {
        // Its symbol list is not reliable, so anything taken from it would be a
        // guess. The Problems panel already reports the syntax error, which is
        // the actionable form of the same fact.
        assertThat(TestDiscovery.discover(project(
            "orders.test_totals", "def test_a(:\n"))).isEmpty();
    }

    @Test
    @DisplayName("modules come back in name order")
    void modulesAreSorted() {
        List<TestDiscovery.TestModule> found = TestDiscovery.discover(project(
            "zulu.test_z", "def test_a():\n    pass\n",
            "alpha.test_a", "def test_a():\n    pass\n"));
        assertThat(found).extracting(TestDiscovery.TestModule::module)
            .containsExactly("alpha.test_a", "zulu.test_z");
    }
}
