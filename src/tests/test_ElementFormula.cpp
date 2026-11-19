#include "../core/ElementFormula.h"
#include "../tests/TestUtils.h"

#include "testing/OriTestBase.h"

namespace Z {
namespace Tests {
namespace ElementFormulaTests {

namespace {
class TestParam : public Z::Parameter
{
public:
    TestParam(Ori::Testing::TestBase *test, const QString& name): Z::Parameter(Z::Dims::none(), name), test(test) {}
    ~TestParam() override {
        TEST_LOG("~TestParam() " + alias())
        SET_TEST_DATA(QString("param destructor %1").arg(alias()), true);
    }
    Ori::Testing::TestBase *test;
};
}

#define ASSERT_PARAM_DESTRUCTED(param_alias) \
    ASSERT_IS_TRUE(test->data()[QString("param destructor %1").arg(param_alias)].toBool())

#define ADD_PARAM(name, value) \
    auto p_##name = new TestParam(test, #name);\
    p_##name->setValue(value);\
    elem.addParam(p_##name);

#define ASSERT_MATRIX(ts, a, b, c, d)\
    TEST_LOG(elem.failReason())\
    ASSERT_IS_FALSE(elem.failed())\
    ASSERT_EQ_DBL(elem.M##ts().A.real(), a)\
    ASSERT_EQ_DBL(elem.M##ts().B.real(), b)\
    ASSERT_EQ_DBL(elem.M##ts().C.real(), c)\
    ASSERT_EQ_DBL(elem.M##ts().D.real(), d)\
    ASSERT_EQ_DBL(elem.M##ts().A.imag(), 0)\
    ASSERT_EQ_DBL(elem.M##ts().B.imag(), 0)\
    ASSERT_EQ_DBL(elem.M##ts().C.imag(), 0)\
    ASSERT_EQ_DBL(elem.M##ts().D.imag(), 0)

#define CALC_TEST_MATRIX(code)\
    elem.setFormula(code);\
    elem.calcMatrix("test");

#define ASSERT_ERROR(err) {}\
    TEST_LOG(elem.failReason())\
    ASSERT_IS_TRUE(elem.failed())\
    QString expected_error(err);\
    if (!expected_error.isEmpty())\
        ASSERT_EQ_STR(elem.failReason(), expected_error)


TEST_METHOD(can_calculate_matrix)
{
    ElemFormula elem;

    ADD_PARAM(a, 1)
    ADD_PARAM(b, 2)
    ADD_PARAM(c, 3)
    ADD_PARAM(d, 4)

    CALC_TEST_MATRIX(
        "from rezonator import Matrix\n"
        "def calc_matrix(elem):\n"
        "    a = elem.param('a')\n"
        "    b = elem.param('b')\n"
        "    c = elem.param('c')\n"
        "    d = elem.param('d')\n"
        "    return {'Mt': Matrix(a, b, c, d), 'Ms': Matrix(10*a, 10*b, 10*c, 10*d)}\n")

    ASSERT_MATRIX(t, 1, 2, 3, 4)
    ASSERT_MATRIX(s, 10, 20, 30, 40)
}

TEST_METHOD(matrix_must_be_unity_when_empty_formula)
{
    ElemFormula elem;
    CALC_TEST_MATRIX("")
    ASSERT_ERROR("无法获取函数 calc_matrix")
    ASSERT_MATRIX_IS_UNITY(elem.Mt())
    ASSERT_MATRIX_IS_UNITY(elem.Ms())
}

TEST_METHOD(matrix_must_be_unity_when_invalid_formula)
{
    ElemFormula elem;
    CALC_TEST_MATRIX(
        "from rezonator import Matrix\n"
        "def calc_matrix(elem):\n"
        "    return {'Mt': Matrix(unknown_func(4), 0, 0, 1), 'Ms': Matrix(1, 0, 0, 1)}\n")
    ASSERT_ERROR("调用函数失败（函数：calc_matrix）")
    ASSERT_MATRIX_IS_UNITY(elem.Mt())
    ASSERT_MATRIX_IS_UNITY(elem.Ms())
}

TEST_CASE_METHOD(matrix_must_be_unity_when_no_abcd, bool hasTS, const char* missedName)
{
    Q_UNUSED(hasTS)
    ElemFormula elem;
    // The formula builds both matrices from named variables;
    // the missed one is not assigned, so calc_matrix fails with NameError.
    QStringList assignments = { "At = 5", "Bt = 6", "Ct = 7", "Dt = 8",
                                "As = 9", "Bs = 10", "Cs = 11", "Ds = 12" };
    QString code = "from rezonator import Matrix\ndef calc_matrix(elem):\n";
    for (const auto &a : assignments)
        if (!a.startsWith(QString(missedName) + " ="))
            code += "    " + a + "\n";
    code += "    return {'Mt': Matrix(At, Bt, Ct, Dt), 'Ms': Matrix(As, Bs, Cs, Ds)}\n";
    CALC_TEST_MATRIX(code)
    ASSERT_ERROR("调用函数失败（函数：calc_matrix）")
    ASSERT_MATRIX_IS_UNITY(elem.Mt())
    ASSERT_MATRIX_IS_UNITY(elem.Ms())
}
TEST_CASE(matrix_must_be_unity_when_no_at, matrix_must_be_unity_when_no_abcd, true, "At")
TEST_CASE(matrix_must_be_unity_when_no_bt, matrix_must_be_unity_when_no_abcd, true, "Bt")
TEST_CASE(matrix_must_be_unity_when_no_ct, matrix_must_be_unity_when_no_abcd, true, "Ct")
TEST_CASE(matrix_must_be_unity_when_no_dt, matrix_must_be_unity_when_no_abcd, true, "Dt")
TEST_CASE(matrix_must_be_unity_when_no_as, matrix_must_be_unity_when_no_abcd, true, "As")
TEST_CASE(matrix_must_be_unity_when_no_bs, matrix_must_be_unity_when_no_abcd, true, "Bs")
TEST_CASE(matrix_must_be_unity_when_no_cs, matrix_must_be_unity_when_no_abcd, true, "Cs")
TEST_CASE(matrix_must_be_unity_when_no_ds, matrix_must_be_unity_when_no_abcd, true, "Ds")

TEST_METHOD(params_in_formula_must_be_in_si_units)
{
    ElemFormula elem;
    auto p = new Z::Parameter(Z::Dims::linear(), "a");
    p->setValue(10_cm);
    elem.addParam(p);
    CALC_TEST_MATRIX(
        "from rezonator import Matrix\n"
        "def calc_matrix(elem):\n"
        "    a = elem.param('a')\n"
        "    return {'Mt': Matrix(a, a, a, a), 'Ms': Matrix(a, a, a, a)}\n")
    ASSERT_MATRIX(t, 0.1, 0.1, 0.1, 0.1)
}

//------------------------------------------------------------------------------

TEST_GROUP("ElementFormula",
           ADD_TEST(can_calculate_matrix),
           ADD_TEST(matrix_must_be_unity_when_empty_formula),
           ADD_TEST(matrix_must_be_unity_when_invalid_formula),
           ADD_TEST(matrix_must_be_unity_when_no_at),
           ADD_TEST(matrix_must_be_unity_when_no_bt),
           ADD_TEST(matrix_must_be_unity_when_no_ct),
           ADD_TEST(matrix_must_be_unity_when_no_dt),
           ADD_TEST(matrix_must_be_unity_when_no_as),
           ADD_TEST(matrix_must_be_unity_when_no_bs),
           ADD_TEST(matrix_must_be_unity_when_no_cs),
           ADD_TEST(matrix_must_be_unity_when_no_ds),
           ADD_TEST(params_in_formula_must_be_in_si_units),
           )

} // namespace ElementFormulaTests
} // namespace Tests
} // namespace Z
