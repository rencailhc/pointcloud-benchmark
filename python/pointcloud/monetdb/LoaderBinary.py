#!/usr/bin/env python
################################################################################
#    Created by Oscar Martinez                                                 #
#    o.rubi@esciencecenter.nl                                                  #
################################################################################
import os, logging, math, numpy
from pointcloud import utils, dbops, monetdbops
from pointcloud.AbstractLoader import AbstractLoader as ALoader
from pointcloud.monetdb.CommonMonetDB import CommonMonetDB

MAX_FILES = 1999

class LoaderBinary(ALoader, CommonMonetDB):
    def __init__(self, configuration):
        """ Set configuration parameters and create user if required """
        ALoader.__init__(self, configuration)
        self.setVariables(configuration)
        
    def connect(self, superUser = False):
        return self.getConnection()     
    
    def initialize(self):
        if self.partitioning and not self.imprints:
            raise Exception('Partitioning without imprints is not supported!')        
        self.numPartitions = 0

        # Drop previous DB if exist and create a new one
        os.system('monetdb stop ' + self.dbName)
        os.system('monetdb destroy ' + self.dbName + ' -f')
        os.system('monetdb create ' + self.dbName)
        os.system('monetdb release ' + self.dbName)
        
        if not self.imprints:
            # If we want to create a final indexed table we need to put the 
            # points in a temporal table
            self.tempFlatTable = 'TEMP_' + self.flatTable
            ftName = self.tempFlatTable
        else:
            ftName = self.flatTable
        
        # Create the point cloud table (a merged table if partitioning is enabled)
        connection = self.connect()
        cursor = connection.cursor()
        merge = ''
        if self.partitioning:
            merge = 'MERGE'
        monetdbops.mogrifyExecute(cursor, "CREATE " + merge + " TABLE " + ftName + " (" + (', '.join(self.getFlatTableCols())) + ")")
        #  Create the meta-data table
        monetdbops.mogrifyExecute(cursor, "CREATE TABLE " + self.metaTable + " (tablename text, srid integer, minx DOUBLE PRECISION, miny DOUBLE PRECISION, maxx DOUBLE PRECISION, maxy DOUBLE PRECISION, scalex DOUBLE PRECISION, scaley DOUBLE PRECISION)")
        # Close connection
        connection.commit()
        connection.close()    
    
    def getFlatTableCols(self):
        cols = []
        for c in self.columns:
            if c not in self.colsData:
                raise Exception('Wrong column!' + c)
            cols.append(self.colsData[c][0] + ' ' + self.colsData[c][1])
        return cols
    
    def close(self):
        # Restart DB to flush data in memory to disk
        logging.info('Restarting DB...')
        os.system('monetdb stop ' + self.dbName)
        os.system('monetdb start ' + self.dbName)
        
        connection = self.connect()
        cursor = connection.cursor()
        
        if not self.imprints:
            ftName = self.tempFlatTable
        else:
            ftName = self.flatTable
        
        # We set the table to read only
        if self.partitioning:
            for i in range(self.numPartitions):
                partitionName = ftName + str(i)
                monetdbops.mogrifyExecute(cursor, "alter table " + partitionName + " set read only")
                connection.commit()
        else:
            monetdbops.mogrifyExecute(cursor, "alter table " + ftName + " set read only")
            connection.commit()
        
        if self.imprints:
            if self.partitioning:
                # Create imprints index
                logging.info('Creating imprints for different partitions and columns...')
                for c in self.columns:
                    colName = self.colsData[c][0]
                    for i in range(self.numPartitions):
                        partitionName = ftName + str(i)
                        monetdbops.mogrifyExecute(cursor, "select " + colName + " from " + partitionName + " where " + colName + " between 0 and 1")
                        connection.commit()
                #TODO create 2 processes, one for x and one for y
            else:
                logging.info('Creating imprints...')
                query = "select * from " + self.flatTable + " where x between 0 and 1 and y between 0 and 1"
                monetdbops.mogrifyExecute(cursor, query)
                connection.commit()
                
        else:
            if self.partitioning:
                for i in range(self.numPartitions):
                    partitionName = ftName + str(i)
                    newPartitionName = self.flatTable + str(i)
                    monetdbops.mogrifyExecute(cursor, 'CREATE TABLE ' + newPartitionName + ' AS SELECT * FROM ' + partitionName + ' ORDER BY ' + dbops.getSelectCols(self.index, self.colsData) + ' WITH DATA')
                    monetdbops.mogrifyExecute(cursor, "alter table " + newPartitionName + " set read only")
                    monetdbops.mogrifyExecute(cursor, 'DROP TABLE ' + partitionName)
                    connection.commit()
            else:
                monetdbops.mogrifyExecute(cursor, 'CREATE TABLE ' + self.flatTable + ' AS SELECT * FROM ' + self.tempFlatTable + ' ORDER BY ' + dbops.getSelectCols(self.index, self.colsData) + ' WITH DATA')
                monetdbops.mogrifyExecute(cursor, "alter table " + self.flatTable + " set read only")
                monetdbops.mogrifyExecute(cursor, 'DROP TABLE ' + self.tempFlatTable)
                connection.commit()
            
        if self.partitioning:
            for i in range(self.numPartitions):
                partitionName = self.flatTable + str(i)
                monetdbops.mogrifyExecute(cursor, "ALTER TABLE " + self.flatTable + " add table " + partitionName)
                connection.commit()
        
        connection.close()
 
    def size(self):
        connection = self.connect()
        cursor = connection.cursor()
        sizes = monetdbops.getSizes(cursor)
        cursor.close()
        connection.close()
        
        for i in range(len(sizes)):
            if sizes[i] != None:
                sizes[i] = '%.3f MB' % sizes[i]
        (size_indexes, size_ex_indexes, size_total) = sizes
        return ' Size indexes= ' + str(size_indexes) + '. Size excluding indexes= ' + str(size_ex_indexes) + '. Size total= ' + str(size_total)
    
    def getNumPoints(self):
        connection = self.connect()
        cursor = connection.cursor()
        cursor.execute('select count(*) from ' + self.flatTable)
        n = cursor.fetchone()[0]
        connection.close()
        return n
    
    def process(self):
        return self.processSingle([self.inputFolder, ], self.processInputFolder)
    
    def processInputFolder(self, index, inputFolder):
        inputFiles = utils.getFiles(inputFolder)
        
        # We get the extent of all the involved PCs
        (_, minX, minY, _, maxX, maxY, _) = lasops.getPCDetails(inputFolder)
        
        # We assume all files have same SRID and scale
        srid = lasops.getSRID(inputFiles[0])
        (_, _, _, _, _, _, _, scaleX, scaleY, _, _, _, _) = getPCFileDetails(inputFiles[0])
        
        # Create connection
        connection = self.connect()
        cursor = connection.cursor()    
        
        # Add the meta-data to the meta table
        metaArgs = (self.flatTable, srid, minX, minY, maxX, maxY, scaleX, scaleY)
        monetdbops.mogrifyExecute(cursor, "INSERT INTO " + self.metaTable + " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)" , metaArgs)

        # Split the list of input files in bunches of maximum MAX_FILES files
        inputFilesLists = numpy.array_split(inputFiles, int(math.ceil(float(len(inputFiles))/float(MAX_FILES))))

        for i in range(len(inputFilesLists)):
            # Create the file with the list of PC files
            listFile =  self.tempDir + '/' + str(i) + '_listFile'
            outputFile = open(listFile, 'w')
            for f in inputFilesLists[i]:
                outputFile.write(f + '\n')
            outputFile.close()
            
            # Generate the command for the NLeSC Binary converter
            inputArg = '-f ' + listFile
            tempFile =  self.tempDir + '/' + str(i) + '_tempFile'    
            c = 'las2col ' + inputArg + ' ' + tempFile + ' --parse ' + self.columns
            if 'k' in self.columns:
                (mortonGlobalOffsetX, mortonGlobalOffsetY) = (minX, minY)
                (mortonScaleX, mortonScaleY) = (scaleX, scaleY)
                c += ' --moffset ' + str(int(self.mortonGlobalOffsetX / self.mortonScaleX)) + ','+ str(int(self.mortonGlobalOffsetY / self.mortonScaleY)) + ' --check ' + str(self.mortonScaleX) + ',' + str(self.mortonScaleY)
            # Execute the converter
            logging.info(c)
            os.system(c)
            
            # The different binary files have a pre-defined name 
            bs = []
            for col in self.columns:
                bs.append("'" + tempFile + "_col_" + col + ".dat'")
            
            if not self.imprints:
                ftName = self.tempFlatTable
            else:
                ftName = self.flatTable
            
            # Import the binary data in the tables
            if self.partitioning:
                partitionName = ftName + str(i)
                monetdbops.mogrifyExecute(cursor, "CREATE TABLE " + partitionName + " (" + (',\n'.join(self.getFlatTableCols())) + ")")
                monetdbops.mogrifyExecute(cursor, "COPY BINARY INTO " + partitionName + " from (" + ','.join(bs) + ")")
                self.numPartitions += 1
            else:
                monetdbops.mogrifyExecute(cursor, "COPY BINARY INTO " + ftName + " from (" + ','.join(bs) + ")")
    
        connection.commit()
        connection.close()
