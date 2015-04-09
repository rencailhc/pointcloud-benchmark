#!/usr/bin/env python
################################################################################
#    Created by Oscar Martinez                                                 #
#    o.rubi@esciencecenter.nl                                                  #
################################################################################
import os, logging
import utils
from pointcloud.oracle.AbstractLoader import AbstractLoader
from pointcloud import lasops, pdalxml

class Loader(AbstractLoader):
    def initialize(self):
        # Check parameters for this loader
        if self.partition != 'none':
            raise Exception('ERROR: partitions are not supported!')
        
        if self.cluster:
            raise Exception('ERROR: clustering is not supported!')
        
        #if self.numProcessesLoad != 1:
        #    raise Exception('ERROR: single process is allowed!')
        
        
        # Creates the user that will store the tables
        if self.cUser:
            self.createUser()
        
        (self.inputFiles, self.srid, _, self.minX, self.minY, _, self.maxX, self.maxY, _, self.scaleX, self.scaleY, _) = getPCFolderDetails(self.inputFolder)
        
        connection = self.getConnection()
        cursor = connection.cursor()
        
        # Creates the global blocks tables
        self.createBlocks(cursor, self.blockTable, self.baseTable, self.tableSpace, includeBlockId = True)
        connection.close()

    def process(self):
        return self.processMulti(self.inputFiles, self.numProcessesLoad, self.loadFromFile, None, True)

    def loadFromFile(self, index, fileAbsPath):
        # Get information of the contents of the LAS file
        logging.debug(fileAbsPath)
        
        #(self.dimensionsNames, pcid, compression, offsets, scales) = self.addPCFormat(self.schemaFile, fileAbsPath)
        (_, _, _, _, _, _, _, scaleX, scaleY, scaleZ, offsetX, offsetY, offsetZ) = lasops.getPCFileDetails(fileAbsPath)  
        offsets = {'X': offsetX, 'Y': offsetY, 'Z': offsetZ}
        scales = {'X': scaleX, 'Y': scaleY, 'Z': scaleZ}
        xmlFile = pdalxml.OracleWriter(fileAbsPath, self.connectString(), self.dimensionsNames, self.blockTable, self.baseTable, self.srid, self.blockSize, offsets, scales)
        c = 'pdal pipeline ' + xmlFile + ' -d -v 6'
        logging.debug(c)
        os.system(c)
        # remove the XML file
        os.system('rm ' + xmlFile)

    def close(self):
        connection = self.getConnection()
        cursor = connection.cursor()
        self.createBlockIdIndex(cursor)
        self.createBlockIndex(cursor, self.minX, self.minY, self.maxX, self.maxY)
        connection.close()
        
    def size(self):
        return self.sizeBlocks()
        
    def getNumPoints(self):
        return self.getNumPointsBlocks()