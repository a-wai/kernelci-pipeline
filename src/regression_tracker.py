#!/usr/bin/env python3
#
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Copyright (C) 2022 Collabora Limited
# Author: Jeny Sadadia <jeny.sadadia@collabora.com>

import sys

import kernelci
import kernelci.config
import kernelci.db
from kernelci.legacy.cli import Args, Command, parse_opts

from base import Service


class RegressionTracker(Service):

    def __init__(self, configs, args):
        super().__init__(configs, args, 'regression_tracker')
        self._regression_fields = [
            'artifacts', 'group', 'name', 'path', 'revision', 'result',
            'state',
        ]

    def _setup(self, args):
        return self._api_helper.subscribe_filters({
            'state': 'done',
        })

    def _stop(self, sub_id):
        if sub_id:
            self._api_helper.unsubscribe_filters(sub_id)

    def _create_regression(self, failed_node, last_successful_node):
        """Method to create a regression"""
        regression = {}
        for field in self._regression_fields:
            regression[field] = failed_node[field]
        regression['parent'] = failed_node['id']
        regression['regression_data'] = [last_successful_node, failed_node]
        self._api_helper.submit_regression(regression)

    def _detect_regression(self, node):
        """Method to check and detect regression"""
        previous_nodes = self._api.get_nodes({
            'name': node['name'],
            'group': node['group'],
            'path': node['path'],
            'revision.tree': node['revision']['tree'],
            'revision.branch': node['revision']['branch'],
            'revision.url': node['revision']['url'],
            'created__lt': node['created'],
        })

        if previous_nodes:
            previous_nodes = sorted(
                previous_nodes,
                key=lambda node: node['created'],
                reverse=True
            )

            if previous_nodes[0]['result'] == 'pass':
                self.log.info(f"Detected regression for node id: \
{node['id']}")
                self._create_regression(node, previous_nodes[0])

    def _get_all_failed_child_nodes(self, failures, root_node):
        """Method to get all failed nodes recursively from top-level node"""
        child_nodes = self._api.get_nodes({'parent': root_node['id']})
        for node in child_nodes:
            if node['result'] == 'fail':
                failures.append(node)
            self._get_all_failed_child_nodes(failures, node)

    def _run(self, sub_id):
        """Method to run regression tracking"""
        self.log.info("Tracking regressions... ")
        self.log.info("Press Ctrl-C to stop.")
        sys.stdout.flush()

        while True:
            node = self._api_helper.receive_event_node(sub_id)

            if node['name'] == 'checkout':
                continue

            failures = []
            self._get_all_failed_child_nodes(failures, node)

            for node in failures:
                self._detect_regression(node)

            sys.stdout.flush()
        return True


class cmd_run(Command):
    help = "Regression tracker"
    args = [Args.api_config]

    def __call__(self, configs, args):
        return RegressionTracker(configs, args).run(args)


if __name__ == '__main__':
    opts = parse_opts('regression_tracker', globals())
    yaml_configs = opts.get_yaml_configs() or 'config/pipeline.yaml'
    configs = kernelci.config.load(yaml_configs)
    status = opts.command(configs, opts)
    sys.exit(0 if status is True else 1)
