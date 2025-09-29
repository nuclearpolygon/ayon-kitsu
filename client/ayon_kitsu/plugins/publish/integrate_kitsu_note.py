# -*- coding: utf-8 -*-
import json
import re

import gazu
import pyblish.api

from ayon_kitsu.pipeline import KitsuPublishContextPlugin
from ayon_core.pipeline import Anatomy


class MDEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, dict):
            encoded_text = ''
            for key, value in obj.items():
                if isinstance(key, (str, int, float, bool, type(None))):
                    encoded_key = f'{key}'
                else:
                    encoded_key = self.encode(key)

                encoded_value = self.encode(value)
                encoded_text += f"{encoded_key}:  \n{encoded_value}\n\n"
            return encoded_text
        elif isinstance(obj, list):
            return '  \n'.join([f'`{item}`  ' for item in obj])
        else:
            return super().encode(obj)

    def default(self, obj):
        return super().default(obj)


class IntegrateKitsuNote(KitsuPublishContextPlugin):
    """Integrate Kitsu Note"""

    order = pyblish.api.IntegratorOrder
    label = "Kitsu Note and Status"
    families = ["kitsu"]

    # status settings
    set_status_note = False
    note_status_shortname = "wfa"
    status_change_conditions = {
        "status_conditions": [],
        "family_requirements": [],
    }

    # comment settings
    custom_comment_template = {
        "enabled": False,
        "comment_template": "{comment}",
    }

    def format_json(self, data):
        return json.dumps(data, cls=MDEncoder)


    def format_publish_comment(self, instance):
        """Format the instance's publish comment

        Formats `instance.data` against the custom template.
        """

        def replace_missing_key(match):
            """If key is not found in kwargs, set None instead"""
            key = match.group(1)
            if key not in instance.data:
                self.log.warning(
                    "Key '{}' was not found in instance.data "
                    "and will be rendered as an empty string "
                    "in the comment".format(key)
                )
                return ""
            elif not isinstance(instance.data[key], str):
                return self.format_json(instance.data[key])
            else:
                return str(instance.data[key])

        template = self.custom_comment_template["comment_template"]
        pattern = r"\{([^}]*)\}"
        return re.sub(pattern, replace_missing_key, template)

    def process(self, context):
        # Backwards compatibility for wront key
        if "product_type_requirements" in self.status_change_conditions:
            family_requirements = self.status_change_conditions[
                "product_type_requirements"
            ]
        else:
            family_requirements = self.status_change_conditions[
                "family_requirements"
            ]

        for instance in context:
            # Check if instance is a review by checking its family
            # Allow a match to primary family or any of families
            families = set(
                [instance.data["family"]] + instance.data.get("families", [])
            )
            if "review" not in families or "kitsu" not in families:
                continue

            kitsu_task = instance.data.get("kitsuTask")
            if not kitsu_task:
                continue

            # Get note status, by default uses the task status for the note
            # if it is not specified in the configuration
            shortname = kitsu_task["task_status"]["short_name"].upper()
            note_status = kitsu_task["task_status_id"]

            # Check if any status condition is not met
            allow_status_change = True
            for status_cond in (
                self.status_change_conditions["status_conditions"]
            ):
                condition = status_cond["condition"] == "equal"
                match = status_cond["short_name"].upper() == shortname
                if match and not condition or condition and not match:
                    allow_status_change = False
                    break

            if allow_status_change:
                # Get families
                families = {
                    instance.data.get("family")
                    for instance in context
                    if instance.data.get("publish")
                }

                # Check if any family requirement is met

                for family_requirement in family_requirements:
                    condition = family_requirement["condition"] == "equal"

                    for family in families:
                        match = family_requirement["family"].lower() == family
                        if match and not condition or condition and not match:
                            allow_status_change = False
                            break

                    if allow_status_change:
                        break

            # Set note status
            if self.set_status_note and allow_status_change:
                kitsu_status = gazu.task.get_task_status_by_short_name(
                    self.note_status_shortname
                )
                if kitsu_status:
                    note_status = kitsu_status
                    self.log.info(f"Note Kitsu status: {note_status}")
                else:
                    self.log.info(
                        f"Cannot find {self.note_status_shortname} status."
                        " The status will not be changed!"
                    )

            published_representations = {}
            anatomy = Anatomy(instance.data['projectEntity']['name'])
            for scene_instance in instance.context:
                for attached_id in (instance.data['publish_attributes']
                        .get('AttachReviewables', {}).get('attach')):
                    if attached_id != scene_instance.data['instance_id']:
                        continue
                    for _repr in scene_instance.data['published_representations'].values():
                        repr_name = _repr["representation"]["name"]
                        if repr_name in ('thumbnail', ):
                            continue
                        repr_file = _repr["representation"]["attrib"]["path"]
                        published_representations[repr_name] = [
                            anatomy.path_remapper(repr_file, 'windows'),
                            anatomy.path_remapper(repr_file, 'linux')
                        ]
            self.log.info(published_representations)
            instance.data['products'] = published_representations
            publish_comment = instance.data.get("comment")
            if self.custom_comment_template["enabled"]:
                publish_comment = self.format_publish_comment(instance)

            if not publish_comment:
                self.log.debug("Comment is not set.")
            else:
                self.log.debug(f"Comment is `{publish_comment}`")

            # Add comment to kitsu task
            self.log.debug(f'Add new note in tasks id {kitsu_task["id"]}')
            kitsu_comment = gazu.task.add_comment(
                kitsu_task, note_status, comment=publish_comment
            )

            instance.data["kitsuComment"] = kitsu_comment
