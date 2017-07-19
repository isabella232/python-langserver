import ast
import os
import os.path
import logging
import runpy
import sys


log = logging.getLogger(__name__)


class SetupVisitor(ast.NodeVisitor):
    """
    The purpose of this class is to crawl over a project's setup.py and statically extract the configuration info that
    we need in order to infer package names, exports, dependencies, etc.
    """
    def __init__(self, workspace, path):
        self.workspace = workspace
        self.name = None
        self.packages = set()
        self.requirements = set()
        self.bindings = {}
        self.path = path

    def visit_Call(self, node):
        """
        Look for calls to `setup`, `find_packages`, and the `dict` constructor.
        :param node: the function call node that we're visiting
        :return: None
        """
        func_name = self.get_func_name(node.func)
        if func_name not in ("setup", "find_packages", "dict"):
            return

        args, kwds = self.get_func_args(node)

        if func_name == "dict":
            return kwds

        if func_name == "find_packages":
            where = os.path.dirname(self.path)
            exclude = ()
            include = ("*",)
            # TODO(aaron): relativize the incoming `where` arg?
            if len(args) > 0:
                where = os.path.join(args[0])
            elif "where" in kwds:
                where = os.path.join(kwds["where"])
            if len(args) > 1:
                exclude = args[1]
            elif "exclude" in kwds:
                exclude = kwds["exclude"]
            if len(args) > 2:
                include = args[2]
            elif "include" in kwds:
                include = kwds["include"]
            return {p for p in self.workspace.find_packages(where, exclude, include)}

        if func_name == "setup":
            self.name = kwds.get("name", None)
            self.packages = set(kwds.get("packages", ()))
            self.requirements = {r for r in kwds.get("install_requires", ())}

    def visit_Assign(self, node):
        """
        Keep track of assignments of vars to literal values, references, and calls to find_packages. Stores everything
        in a single dict and doesn't keep track of nested scopes.
        :param node: the assignment node that we're visiting
        :return:
        """
        vars = [self.eval_lhs(var) for var in node.targets]
        vals = self.eval_rhs(node.value)
        if len(vars) == 1:
            assns = zip(vars, [vals])
        elif type(vals) in (list, tuple, set, dict):
            assns = zip(vars, vals)
        else:
            return
        for var, val in assns:
            self.bindings[var] = val

    @staticmethod
    def eval_lhs(node):
        """
        Evaluates an l-value (i.e., figures out the name on the left hand side of an assignment).
        :param node: the left-hand-side of the assignment
        :return:
        """
        if type(node) is ast.Name:
            return node.id
        elif type(node) is ast.NameConstant:
            return node.value
        elif type(node) is ast.Attribute:
            return node.attr
        else:
            return None

    def eval_rhs(self, node):
        """
        Evaluates an r-value (i.e., a "normal" expression that produces a first-class value). Names are looked up in
        the simple environment that we maintain, calls are handled by `visit_Call`, and everything else falls back on
        `ast.literal_eval`.
        :param node: the expression to evaluate
        :return:
        """
        if type(node) is ast.Name:
            return self.bindings.get(node.id, None)
        elif type(node) is ast.NameConstant:
            return self.bindings.get(node.value, None)
        elif type(node) is ast.Attribute:
            return self.bindings.get(node.attr, None)
        elif type(node) is ast.Call:  # only handle calls to find_packages
            return self.visit_Call(node)
        else:
            try:
                return ast.literal_eval(node)
            except ValueError:
                return None

    @staticmethod
    def get_func_name(node):
        if type(node) is ast.NameConstant:
            return node.value
        elif type(node) is ast.Name:
            return node.id
        elif type(node) is ast.Attribute:
            return node.attr
        else:
            return None

    def get_func_args(self, node):
        if type(node) is not ast.Call:
            args, kwds = [], {}
        else:
            args = [self.eval_rhs(arg) for arg in node.args]
            kwds = {kwd.arg: self.eval_rhs(kwd.value) for kwd in node.keywords}
            if len(kwds) == 1 and None in kwds:  # handle "splatted" args
                kwds = kwds[None]
        return args, kwds


def upset(src, path, workspace):
    tree = ast.parse(src, "setup.py")
    visitor = SetupVisitor(workspace, path)
    visitor.visit(tree)
    return visitor


def setup_info(setup_file):
    """Returns metadata for a PyPI package by running its setup.py"""
    setup_dict = {}

    def setup_replacement(**kw):
        iterator = kw.items()
        for k, v in iterator:
            setup_dict[k] = v

    setuptools_mod = __import__('setuptools')
    import distutils.core  # for some reason, __import__('distutils.core') doesn't work

    # Mod setup()
    old_setuptools_setup = setuptools_mod.setup
    setuptools_mod.setup = setup_replacement
    old_distutils_setup = distutils.core.setup
    distutils.core.setup = setup_replacement
    # Mod sys.path (changing sys.path is necessary in addition to changing the working dir,
    # because of Python's import resolution order)
    old_sys_path = list(sys.path)
    sys.path.insert(0, os.path.dirname(setup_file))
    # Change working dir (necessary because some setup.py files read relative paths from the filesystem)
    old_wd = os.getcwd()
    os.chdir(os.path.dirname(setup_file))
    # Redirect stdout to stderr (*including for subprocesses*)
    old_sys_stdout = sys.stdout  # redirects in python process
    sys.stdout = sys.stderr
    old_stdout = os.dup(1)  # redirects in subprocesses
    stderr_dup = os.dup(2)
    os.dup2(stderr_dup, 1)

    try:
        runpy.run_path(os.path.basename(setup_file), run_name='__main__')
    finally:
        # Restore stdout
        os.dup2(old_stdout, 1)  # restores for subprocesses
        os.close(stderr_dup)
        sys.stdout = old_sys_stdout  # restores for python process
        # Restore working dir
        os.chdir(old_wd)
        # Restore sys.path
        sys.path = old_sys_path
        # Restore setup()
        distutils.core.setup = old_distutils_setup
        setuptools_mod.setup = old_setuptools_setup

    return setup_dict
