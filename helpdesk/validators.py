# validators.py
#
# validators for file uploads, etc.

from django.conf import settings
from django.core.exceptions import ValidationError

#TODO: can we use the builtin Django validator instead?
# see: https://docs.djangoproject.com/en/4.0/ref/validators/#fileextensionvalidator
def validate_file_extension(value):
    import os
    ext = os.path.splitext(value.name)[1]  # [0] returns path+filename
    # TODO: we might improve this with more thorough checks of file types
    # rather than just the extensions.

    # check if VALID_EXTENSIONS is defined in settings.py
    # if not use defaults

    if hasattr(settings, 'VALID_EXTENSIONS'):
        valid_extensions = settings.VALID_EXTENSIONS
    else:
        valid_extensions = ['.txt', '.pdf', '.doc', '.docx', '.odt', '.jpg', '.png', '.eml', '.mp4', '.gif', '.mkv', '.nivo']

    if not ext.lower() in valid_extensions:
        raise ValidationError('Unsupported file extension.')



# * add by sia
def validate_file_size(value):

    #  file size file size
    # megabyte to byte
    size = {
        '5MB': 5242880,
        '10MB': 10485760,
        '20MB': 20971520,
        '50MB': 52428800,
        '100MB': 104857600,
        '250MB': 262144000,
        '500MB': 524288000,
    }

    filesize= value.size
    accepted_size = size['50MB']
    if filesize > accepted_size:
        raise ValidationError("The maximum file size that can be uploaded is {}".format(accepted_size))
