import tensorflow as tf
from covid19.models._model import Model
from covid19.layers import Rescaling
from tensorflow.keras import Sequential
from tensorflow.keras.applications import ResNet50V2
from tensorflow.keras.layers import Dense, GlobalAveragePooling2D


class ResNet50(Model):
    """
    COVID-19 detection model with ResNet50v2 as convolutional base for feature extraction.

    Inputs: batches of images with shape (None, 224, 224, 3).
    Outputs: batches of softmax activations (None, n_classes).
    """

    def __init__(self, n_classes, name='resnet50', weights='imagenet'):
        """
        :param n_classes: int, number of classes (units in the last layer)
        :param name: string, name of the model
        :param weights: one of 'imagenet', None or path to the weights to load
        """
        super().__init__(name=name)
        self._image_shape = (224, 224, 3)
        self._n_classes = n_classes
        self._from_scratch = weights is None

        if weights is not None and weights != 'imagenet':   # weights for the whole model
            load = True
            weights_resnet = None
        else:
            load = False
            weights_resnet = weights

        self._feature_extractor = Sequential([
            Rescaling(1./127.5, offset=-1),
            ResNet50V2(include_top=False, weights=weights_resnet, input_shape=self.image_shape)
        ], name='feature_extractor')

        self._classifier = Sequential([
            GlobalAveragePooling2D(),
            Dense(n_classes, activation='softmax')
        ], name='classifier')

        if load:
            self.load_weights(weights)

        self.build(input_shape=(None, self.image_shape[0], self.image_shape[1], self.image_shape[2]))

    def call(self, inputs, training=None, mask=None):
        # remarks:
        # - using Rescaling layer, tf.data.Dataset and tf.keras.Model.fit() causes unknown shape... reshaping fixes
        #   see https://gitmemory.com/issue/tensorflow/tensorflow/24520/511633717
        # - if we are using pre-trained weights (self._from_scratch=True), BN layers must be kept in inference mode
        #   see https://www.tensorflow.org/tutorials/images/transfer_learning
        x = tf.reshape(inputs, tf.constant((-1,) + self.image_shape))
        x = self.feature_extractor(x, training=False if self._from_scratch else training)
        x = self.classifier(x)
        return x

    def get_config(self):
        config = super().get_config()
        config.update({'n_classes': self._n_classes})
        return config

    def fit_linear_classifier(self, learning_rate, loss, metrics, train_ds, val_ds, epochs, initial_epoch, callbacks,
                              class_weights=None):
        self.feature_extractor.trainable = False
        return self.compile_and_fit(learning_rate, loss, metrics, train_ds, val_ds, epochs, initial_epoch, callbacks,
                                    class_weights)

    def fine_tune(self, learning_rate, loss, metrics, train_ds, val_ds, epochs, initial_epoch, callbacks, fine_tune_at,
                  class_weights=None):
        if fine_tune_at > len(self.feature_extractor.layers):
            raise ValueError('Too big fine_tune_at, more than the number of layers')
        self.feature_extractor.trainable = True     # unfreeze convolutional base
        for layer in self.feature_extractor.layers[:fine_tune_at]:
            layer.trainable = False                 # freeze bottom layers
        return self.compile_and_fit(learning_rate, loss, metrics, train_ds, val_ds, epochs, initial_epoch, callbacks,
                                    class_weights)

    @property
    def feature_extractor(self):
        return self._feature_extractor

    @property
    def classifier(self):
        return self._classifier

    @property
    def image_shape(self):
        return self._image_shape
