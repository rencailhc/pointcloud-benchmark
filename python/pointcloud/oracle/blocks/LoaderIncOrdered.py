#!/usr/bin/env python
################################################################################
#    Created by Oscar Martinez                                                 #
#    o.rubi@esciencecenter.nl                                                  #
################################################################################
import logging
from pointcloud import utils
from pointcloud.oracle.AbstractLoader import AbstractLoader

class LoaderIncOrdered(AbstractLoader):
    def initialize(self):
        # Check parameters for this loader
        if self.partition != 'none':
            raise Exception('ERROR: partitions are not supported!')
        
        if self.cluster:
            raise Exception('ERROR: clustering is not supported!')
        
        # Creates the user that will store the tables
        self.createUser()
        
        if self.cUser:
            connection = self.connect()
            cursor = connection.cursor()
            
            # Creates the global blocks tables
            self.createBlocks(cursor, self.blockTable, self.baseTable)
            self.blockSeq = self.blockTable + '_ID_SEQ'
            cursor.execute("create sequence " + self.blockSeq )
            connection.commit()
            self.initCreatePC(cursor, create = False)
            connection.commit() 
            connection.close()

    def getFileBlockTable(self, index):
        return self.blockTable + '_' + str(index)

#    def getFileBlockSeq(self, index):
#        return self.getFileBlockTable(index) + '_ID_SEQ'

    def process(self):
        inputFiles = utils.getFiles(self.inputFolder)
        return self.processMulti(inputFiles, self.numProcessesLoad, self.loadFromFile, self.loadFromFileSequential, True)

    def loadFromFile(self,  index, fileAbsPath):
        #objId = index
        objId = 1
        blockTable = self.getFileBlockTable(index)
        blockSeq = self.blockSeq
        connection = self.connect()
        cursor = connection.cursor()
        self.createBlocks(cursor, blockTable, None, self.workTableSpace)
        connection.commit()
        connection.close()
        self.loadInc(fileAbsPath, objId, blockTable, blockSeq)
        
    def loadFromFileSequential(self, fileAbsPath, index, numFiles):
        fileBlockTable = self.getFileBlockTable(index)
        connection = self.connect()
        cursor = connection.cursor()
#        query = "INSERT INTO " + self.blockTable + " SELECT * FROM " + fileBlockTable + ' ORDER BY BLK_ID' 
        query = "INSERT INTO " + self.blockTable + " SELECT * FROM " + fileBlockTable
        self.mogrifyExecute(cursor, query)
        connection.commit()
        self.mogrifyExecute(cursor, "DROP TABLE " + fileBlockTable)
        connection.commit()
        
    def close(self):
        connection = self.connect()
        cursor = connection.cursor()
        self.mogrifyExecute(cursor, "update " + self.blockTable + " b set b.blk_extent.sdo_srid = " + str(self.srid))
        self.createBlockIndex(cursor)
        connection.close()
        
    def size(self):
        return self.sizeBlocks()
        
    def getNumPoints(self):
        return self.getNumPointsBlocks()
