# No data sources required here for the Developer / Community Edition.
#
# The previous aws_subnet lookups supported the ECS/ALB hosting layer, which is
# not part of this edition (the Primary Runtime runs locally — see main.tf).
# data.aws_caller_identity.current lives in main.tf.
