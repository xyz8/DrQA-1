import tensorflow as tf
class model(object):
    def __init__(self,config):
        self.config = config
        self.batch_size=  config.batch_size
        self.num_units  = config.num_units
        self.src_vocab_size  = config.src_vocab_size
        self.input_embedding_size = config.input_embedding_size
    def build_model(self):
        # passage
        # as time-major
        with tf.variable_scope("input") as scope:
            # time major
            self.passage_inputs = tf.placeholder(shape=(None,self.batch_size), dtype=tf.int32, name='self.passage_inputs')
            self.passage_sequence_length = tf.placeholder(shape=([self.batch_size]), dtype=tf.int32, name='passage_length')
            # query
            self.query_inputs = tf.placeholder(shape=(None,self.batch_size), dtype=tf.int32, name='self.query_inputs')
            self.query_sequence_length = tf.placeholder(shape=([self.batch_size]), dtype=tf.int32, name='query_length')
            # answer_pi
            self.passage_start_pos =  tf.placeholder(shape=([self.batch_size]), dtype=tf.int32, name='self.passage_start_pos')
            self.passage_end_pos =  tf.placeholder(shape=([self.batch_size]), dtype=tf.int32, name='passage_end_pos')
            self.passage_logit_pro_start =tf.one_hot(self.passage_start_pos, depth= tf.reduce_max(self.passage_sequence_length) )     #tf.placeholder(shape=(1, passage_max), dtype=tf.int32, name='self.passage_logit_pro_start')
            self.passage_logit_pro_end = tf.one_hot(self.passage_end_pos,    depth= tf.reduce_max(self.passage_sequence_length) )  #tf.placeholder(shape=(1, passage_max), dtype=tf.int32, name='self.passage_logit_pro_end')
            # embedding
            # TODO: -1 is because we add <unk> to vocab
            self.embedding_placeholder = tf.placeholder(tf.float32, [self.src_vocab_size -1, self.input_embedding_size])

        #     embeddings = tf.get_variable('passage_embedding',[self.src_vocab_size, self.input_embedding_size],
        #                                                        initializer=tf.random_uniform_initializer(-0.1, 0.1, seed=123),
        #                                                         dtype=tf.float32)
            # TODO: -1 is because we add <unk> to vocab
            embeddings = tf.Variable(tf.constant(0.0, shape=[self.src_vocab_size -1, self.input_embedding_size]),
                            trainable=False, name="W")
            # embedding intial assgin op
            embedding_init = embeddings.assign(self.embedding_placeholder)

            passage_inputs_embedded = tf.nn.embedding_lookup(embeddings, self.passage_inputs)
            query_inputs_embedded = tf.nn.embedding_lookup(embeddings, self.query_inputs)
            # set global_step
            global_step = tf.Variable(0, trainable=False)
        with tf.name_scope("passage_rnn") as scope:
            forward_cell = tf.contrib.rnn.GRUCell(self.num_units)
            backward_cell = tf.contrib.rnn.GRUCell(self.num_units)
            with tf.variable_scope('passage_dynamic_rnn'):
                # time_major -> False: (batch, time step, input); True: (time step, batch, input)
                bi_outputs, encoder_state = tf.nn.bidirectional_dynamic_rnn(
                    forward_cell, backward_cell, passage_inputs_embedded,
                    sequence_length=self.passage_sequence_length, time_major=True,dtype = tf.float32)
                # the size of passage_outputs is  [words_number, self.batch_size, hidden_contact_vector_length]
                passage_outputs = tf.concat(bi_outputs, -1)
            passage_shape = passage_outputs.get_shape().as_list()

        with tf.name_scope("question_rnn") as scope:
            with tf.variable_scope('w'):
                # W shape is [1,1,400]
                W = tf.Variable(tf.truncated_normal([passage_shape[2],1], stddev=0.1))

            with tf.variable_scope('forward'):
                q_forward_cell = tf.contrib.rnn.GRUCell(self.num_units)
            with tf.variable_scope('backward'):
                q_backward_cell = tf.contrib.rnn.GRUCell(self.num_units)
            with tf.variable_scope('question_dynamic_rnn'):
                q_bi_outputs, q_encoder_state = tf.nn.bidirectional_dynamic_rnn(
                    q_forward_cell, q_backward_cell, query_inputs_embedded,
                    sequence_length=self.query_sequence_length, time_major=True,dtype = tf.float32)
            #<tf.Tensor 'concat:0' shape=(?, self.batch_size, hidden_units*2) dtype=float32>
            question_outputs  = tf.concat(q_bi_outputs, -1)
            # a list of [?,400],len is self.batch_size
            question_outputs_unstack  = tf.unstack(question_outputs,axis=1)
            # a list of [?,1] , len is self.batch_size
            result_b =  [tf.nn.softmax(tf.matmul(item ,W),dim=0) for item in question_outputs_unstack]
            # stack of question_outputs_unstack shape is [?,400,self.batch_size]
            question_stakced  =tf.stack(question_outputs_unstack,-1)
            # stack of result_b, shape is [?,1,self.batch_size]
            question_weighted  = tf.stack(result_b,-1)
            # final_queryshape is [400,self.batch_size]
            # question_stakced *  question_weighted shape=(?, 400, 6)
            final_query = tf.reduce_sum(question_stakced *  question_weighted ,axis =0)
        with tf.name_scope('g') as scope:

            passage_outputs_unstack =  tf.unstack(passage_outputs,axis =1)

            with tf.name_scope("pre_q_start") as scope:
                Ws =  tf.Variable(tf.truncated_normal([400,400], stddev=0.1))
                W_q = tf.matmul(Ws,final_query)
                W_q = tf.reshape(W_q , shape=[400,1,self.batch_size])
                # self.p_W_q shape is [?,self.batch_size]
                W_q_unstacked = tf.unstack(W_q,axis =2)

                self.p_W_q = []
                for i in range(self.batch_size):
                    self.p_W_q.append(tf.matmul(passage_outputs_unstack[i] ,W_q_unstacked[i]))
                self.p_W_q = tf.concat(self.p_W_q,axis= -1)
                self.p_W_q = tf.transpose(self.p_W_q ,[1,0])

            with tf.name_scope("pre_q_end") as scope:
                We =  tf.Variable(tf.truncated_normal([400,400], stddev=0.1))
                We_q = tf.matmul(We,final_query)
                We_q = tf.reshape(We_q , shape=[400,1,self.batch_size])
                We_q_unstacked = tf.unstack(We_q,axis =2)
                self.p_We_q = []
                for i in range(self.batch_size):
                    self.p_We_q.append(tf.matmul(passage_outputs_unstack[i] ,We_q_unstacked[i]))
                self.p_We_q = tf.concat(self.p_We_q,axis= -1)
                self.p_We_q = tf.transpose(self.p_We_q ,[1,0])

        if self.config.is_training is False :
            # I need to see probalities:
            self.end_pro = tf.nn.softmax(self.p_We_q)
            self.start_pro = tf.nn.softmax(self.p_W_q)
            return
        with tf.name_scope("compute_loss") as scope:
            # start point
            pre_q_e_loss = tf.nn.softmax_cross_entropy_with_logits(labels= self.passage_logit_pro_end, logits=self.p_We_q)
            cross_entropy_end = tf.reduce_mean(pre_q_e_loss)
            # end point
            pre_q_s_loss = tf.nn.softmax_cross_entropy_with_logits(labels= self.passage_logit_pro_start,logits=self.p_W_q)
            cross_entropy_start = tf.reduce_mean(pre_q_s_loss)
        with tf.name_scope("train_op") as scope:
            coss_all = cross_entropy_start + cross_entropy_end
            parameters = tf.trainable_variables()
            gradients = tf.gradients(coss_all, parameters)
            clipped_gradients, gradient_norm = tf.clip_by_global_norm(gradients, max_gradient_norm)

            """add train op"""
            optimizer = tf.train.AdamOptimizer( learning_rate)
            # Attention: here self.global_step will increment by one after the variables have been updated.
            train_op = optimizer.apply_gradients(zip(clipped_gradients, parameters),global_step= global_step)

            tf.summary.scalar("Training_Loss", coss_all)
            #tf.summary.scalar("learning_rate", learning_rate)
            tf.summary.scalar("gradient_norm", gradient_norm)

            tf.summary.histogram("Ws",Ws)

            tf.summary.histogram("embeddings",embeddings)

            tf.summary.histogram("We",We)
            summary_op = tf.summary.merge_all()