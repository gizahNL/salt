# -*- coding: utf-8 -*-
"""
    tests.support.pytest.loader
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Salt's Loader PyTest Mock Support
"""
import functools
import logging
import sys
import types

import attr  # pylint: disable=3rd-party-module-not-gated
import salt.utils.functools
from tests.support.mock import patch

log = logging.getLogger(__name__)


@attr.s(init=True, slots=True, frozen=True)
class LoaderModuleMock:

    request = attr.ib(init=True)
    setup_loader_modules = attr.ib(init=True)
    salt_dunders = attr.ib(
        init=True,
        repr=False,
        kw_only=True,
        default=(
            "__opts__",
            "__salt__",
            "__runner__",
            "__context__",
            "__utils__",
            "__ext_pillar__",
            "__thorium__",
            "__states__",
            "__serializers__",
            "__ret__",
            "__grains__",
            "__pillar__",
            "__sdb__",
            # Proxy is commented out on purpose since some code in salt expects a NameError
            # and is most of the time not a required dunder
            # '__proxy__'
        ),
    )

    def __enter__(self):
        module_globals = {dunder: {} for dunder in self.salt_dunders}
        for module, globals_to_mock in self.setup_loader_modules.items():
            log.trace(
                "Setting up loader globals for %s; globals: %s", module, globals_to_mock
            )
            if not isinstance(module, types.ModuleType):
                raise RuntimeError(
                    "The dictionary keys returned by setup_loader_modules() "
                    "must be an imported module, not {}".format(type(module))
                )
            if not isinstance(globals_to_mock, dict):
                raise RuntimeError(
                    "The dictionary values returned by setup_loader_modules() "
                    "must be a dictionary, not {}".format(type(globals_to_mock))
                )
            for key in globals_to_mock:
                if key == "sys.modules":
                    sys_modules = globals_to_mock[key]
                    if not isinstance(sys_modules, dict):
                        raise RuntimeError(
                            "'sys.modules' must be a dictionary not: {}".format(
                                type(sys_modules)
                            )
                        )
                    patcher = patch.dict(sys.modules, sys_modules)
                    patcher.start()

                    def cleanup_sys_modules(patcher, sys_modules):
                        patcher.stop()
                        del patcher
                        del sys_modules

                    self.request.addfinalizer(
                        functools.partial(cleanup_sys_modules, patcher, sys_modules)
                    )
                    continue
                if key not in self.salt_dunders:
                    raise RuntimeError("Don't know how to handle key {}".format(key))

                mocked_details = globals_to_mock[key]
                for mock_key, mock_data in mocked_details.items():
                    module_globals[key][mock_key] = mock_data

            # Now that we're done injecting the mocked functions into module_globals,
            # those mocked functions need to be namespaced
            for key in globals_to_mock:
                mocked_details = globals_to_mock[key]
                for mock_key in mocked_details:
                    mock_value = mocked_details[mock_key]
                    if isinstance(mock_value, types.FunctionType):
                        module_globals[key][
                            mock_key
                        ] = salt.utils.functools.namespaced_function(
                            mock_value, module_globals, preserve_context=True
                        )
                        continue
                    module_globals[key][mock_key] = mock_value

            for key in module_globals:
                if not hasattr(module, key):
                    if key in self.salt_dunders:
                        setattr(module, key, {})
                    else:
                        setattr(module, key, None)
                    self.request.addfinalizer(functools.partial(delattr, module, key))

            log.trace(
                "Patching loader globals for %s; globals: %s", module, module_globals
            )
            patcher = patch.multiple(module, **module_globals)
            patcher.start()

            def cleanup_module_globals(patcher, module_globals):
                patcher.stop()
                del patcher
                module_globals.clear()
                del module_globals

            self.request.addfinalizer(
                functools.partial(cleanup_module_globals, patcher, module_globals)
            )
        return self

    def __exit__(self, *args):
        pass
